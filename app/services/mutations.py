"""
app/services/mutations.py
==========================
All write / mutation handlers for the chatbot pipeline.
Handles: clock_in, clock_out, apply_leave, approve_leave, reject_leave,
         post_announcement, create_event, update_event, delete_event,
         assign_task, update_task_status

Extracted from unified_server.py (lines 712-964).
Called from the main slm_chat endpoint in unified_server.py.
"""
import datetime as dt
import logging
from typing import Dict, Any

from app.rbac_rules import check_permission
from binding import supabase

logger = logging.getLogger(__name__)


async def handle_mutation(
    action: str,
    params: Dict[str, Any],
    request,   # SLMQueryRequest
    user_id: str,
    org_id: str,
    project_id: str,
) -> str:
    """
    Dispatch and execute a mutation action.
    Returns data_context string: "SUCCESS: ..." or "ERROR: ..."
    """
    current_now = dt.datetime.now()
    today       = current_now.strftime("%Y-%m-%d")
    now_time    = current_now.strftime("%H:%M:%S")

    try:
        if action == "clock_in":
            return await _clock_in(user_id, today, now_time, request)

        elif action == "clock_out":
            return await _clock_out(user_id, today, now_time)

        elif action == "apply_leave":
            return await _apply_leave(params, user_id, today, request)

        elif action in ["approve_leave", "reject_leave"]:
            return await _approve_reject_leave(action, params, request)

        elif action in ["post_announcement", "create_event"]:
            return await _post_announcement(action, params, request, user_id, today, now_time)

        elif action == "assign_task":
            return await _assign_task(params, request, user_id, org_id, project_id)

        elif action == "update_task_status":
            return await _update_task_status(params, request)

        elif action == "update_event":
            return await _update_event(params, request)

        elif action == "delete_event":
            return await _delete_event(params, request)

        return f"ERROR: Unknown mutation action '{action}'."

    except Exception as e:
        logger.error(f"Mutation error [{action}]: {e}")
        return f"ERROR: Failed to perform {action} due to a system error."


# ---------------------------------------------------------------------------
# Individual mutation handlers
# ---------------------------------------------------------------------------

async def _clock_in(user_id, today, now_time, request) -> str:
    check = await supabase.table("attendance").select("id").eq("employee_id", user_id).eq("date", today).execute()
    if not check.data:
        await supabase.table("attendance").insert({
            "employee_id": user_id, "date": today,
            "clock_in": now_time, "org_id": request.org_id
        }).execute()
        return f"SUCCESS: Clocked in at {now_time} on {today}."
    return f"ERROR: You are already clocked in for today ({today})."


async def _clock_out(user_id, today, now_time) -> str:
    res = await supabase.table("attendance").update({"clock_out": now_time}).eq("employee_id", user_id).eq("date", today).execute()
    if res.data:
        return f"SUCCESS: Clocked out at {now_time}."
    return "ERROR: No clock-in record found for today. Please clock in first."


async def _apply_leave(params, user_id, today, request) -> str:
    leave_data = {
        "employee_id": user_id,
        "from_date":   params.get("from_date") or params.get("start_date") or today,
        "to_date":     params.get("to_date")   or params.get("end_date")   or today,
        "reason":      f"{params.get('type', 'Casual')}: {params.get('reason', 'Applied via Chat')}",
        "status":      "pending",
        "org_id":      request.org_id,
        "team_id":     request.team_id,
    }
    res = await supabase.table("leaves").insert(leave_data).execute()
    if res.data:
        return f"SUCCESS: Leave request submitted from {leave_data['from_date']} to {leave_data['to_date']}."
    return "ERROR: Failed to submit leave request."


async def _approve_reject_leave(action, params, request) -> str:
    if not check_permission(request.user_role, action):
        return "ERROR: You don't have permission to approve or reject leave requests. Only managers and executives can perform this action."

    employee_name = params.get("employee_name")
    if not employee_name:
        return "ERROR: Please specify whose leave request you want to approve/reject. Example: 'approve leave for John'."

    emp_res = await supabase.table("profiles").select("id, full_name").ilike("full_name", f"%{employee_name}%").eq("org_id", request.org_id).execute()
    if not emp_res.data:
        return f"ERROR: Could not find an employee named '{employee_name}' in your organization."

    emp_id   = emp_res.data[0]["id"]
    emp_name = emp_res.data[0]["full_name"]

    leave_res = await supabase.table("leaves").select("id, from_date, to_date").eq("employee_id", emp_id).eq("status", "pending").order("created_at", desc=True).limit(1).execute()
    if not leave_res.data:
        return f"ERROR: No pending leave requests found for {emp_name}."

    leave_id    = leave_res.data[0]["id"]
    leave_dates = f"{leave_res.data[0]['from_date']} to {leave_res.data[0]['to_date']}"
    new_status  = "approved" if action == "approve_leave" else "rejected"
    update_data = {"status": new_status}

    rejection_reason = params.get("reason", "")
    if action == "reject_leave" and rejection_reason:
        update_data["rejection_reason"] = rejection_reason

    res = await supabase.table("leaves").update(update_data).eq("id", leave_id).execute()
    if res.data:
        if action == "approve_leave":
            return f"SUCCESS: Leave for {emp_name} ({leave_dates}) has been approved."
        reason_text = f" Reason: {rejection_reason}" if rejection_reason else ""
        return f"SUCCESS: Leave for {emp_name} ({leave_dates}) has been rejected.{reason_text}"
    return f"ERROR: Failed to update leave status for {emp_name}."


async def _post_announcement(action, params, request, user_id, today, now_time) -> str:
    is_privileged  = check_permission(request.user_role, action)
    target_audience = "all"
    target_employees = []

    if not is_privileged:
        target_audience = "employee"
        if request.project_id:
            m_res = await supabase.table("project_members").select("user_id").eq("project_id", request.project_id).execute()
            target_employees = [m["user_id"] for m in m_res.data] if m_res.data else []
        if not target_employees:
            target_employees = [user_id]

    start_time_raw = params.get("start_time", "")
    event_time     = params.get("event_time") or (start_time_raw.split("T")[-1] if "T" in start_time_raw else now_time)
    event_date     = params.get("event_date") or params.get("start_date") or today
    if event_date and "T" in event_date:
        event_date = event_date.split("T")[0]

    ann_data = {
        "title":       params.get("title") or params.get("headline") or ("New Event" if action == "create_event" else "Announcement"),
        "message":     params.get("content") or params.get("message") or params.get("description") or "",
        "event_for":   target_audience,
        "employees":   target_employees,
        "org_id":      request.org_id,
        "created_at":  dt.datetime.now().isoformat(),
        "event_date":  event_date,
        "event_time":  event_time,
        "location":    params.get("location") or "Broadcast",
    }
    res = await supabase.table("announcements").insert(ann_data).execute()
    if res.data:
        label    = "Event" if action == "create_event" else "Announcement"
        audience = "everyone" if target_audience == "all" else "your team"
        return f"SUCCESS: {label} '{ann_data['title']}' has been posted to {audience}."
    return f"ERROR: Failed to post {action}."


async def _assign_task(params, request, user_id, org_id, project_id) -> str:
    a_name        = params.get("assignee_name") or params.get("user_name")
    target_user_id = params.get("user_id") or params.get("assignee_id")

    if a_name and not target_user_id:
        u_res = await supabase.table("profiles").select("id, full_name").ilike("full_name", f"%{a_name}%").eq("org_id", request.org_id).execute()
        if u_res.data:
            target_user_id = u_res.data[0]["id"]
            a_name         = u_res.data[0]["full_name"]

    if not target_user_id and not a_name:
        target_user_id = user_id
        a_name         = "Self"

    if not target_user_id:
        return f"ERROR: I couldn't find a user named '{a_name}' in this organization."

    task_data = {
        "title":             params.get("title") or "New Task",
        "description":       params.get("description") or "Assigned via Chat",
        "assigned_to":       target_user_id,
        "assigned_to_name":  a_name or "Team Member",
        "assigned_by":       user_id,
        "assigned_by_name":  request.context.get("name") if request.context else "Manager",
        "status":            "pending",
        "priority":          params.get("priority", "medium"),
        "due_date":          params.get("due_date"),
        "org_id":            org_id or request.org_id,
        "project_id":        project_id or request.project_id,
        "allocated_hours":   8,
        "lifecycle_state":   "requirement_refiner",
        "sub_state":         "in_progress",
    }
    try:
        res = await supabase.table("tasks").insert(task_data).execute()
        if res.data:
            return f"SUCCESS: Task '{task_data['title']}' has been assigned to {a_name}."
        return f"ERROR: Database rejected the task assignment. Please include title, assignee name, priority, and deadline clearly."
    except Exception as e:
        return f"ERROR: Database rejected the task assignment. Technical reason: {str(e)}"


async def _update_task_status(params, request) -> str:
    t_title    = params.get("title") or params.get("task_name")
    new_status = params.get("status") or "completed"
    if not t_title:
        return "ERROR: No task title provided for status update."
    find_res = await supabase.table("tasks").select("id").ilike("title", f"%{t_title}%").eq("org_id", request.org_id).execute()
    if find_res.data:
        task_id = find_res.data[0]["id"]
        await supabase.table("tasks").update({"status": new_status}).eq("id", task_id).execute()
        return f"SUCCESS: Status of task '{t_title}' updated to {new_status}."
    return f"ERROR: Could not find any task matching '{t_title}'."


async def _update_event(params, request) -> str:
    event_id    = params.get("event_id")
    event_title = params.get("title")
    update_data = {k: v for k, v in params.items() if k in ["title", "description", "start_time", "end_time", "location", "status"]}

    if not event_id and event_title:
        find_res = await supabase.table("events").select("id").ilike("title", f"%{event_title}%").eq("org_id", request.org_id).execute()
        if find_res.data:
            event_id = find_res.data[0]["id"]
        else:
            return f"ERROR: Could not find any event matching '{event_title}'."

    if not event_id:
        return "ERROR: No event ID or title provided for update."

    res = await supabase.table("events").update(update_data).eq("id", event_id).execute()
    if res and res.data:
        return f"SUCCESS: Event '{event_title or event_id}' updated."
    return f"ERROR: Failed to update event '{event_title or event_id}'."


async def _delete_event(params, request) -> str:
    event_id    = params.get("event_id")
    event_title = params.get("title")

    if not event_id and event_title:
        find_res = await supabase.table("events").select("id").ilike("title", f"%{event_title}%").eq("org_id", request.org_id).execute()
        if find_res.data:
            event_id = find_res.data[0]["id"]
        else:
            return f"ERROR: Could not find any event matching '{event_title}'."

    if not event_id:
        return "ERROR: No event ID or title provided for deletion."

    res = await supabase.table("events").delete().eq("id", event_id).execute()
    if res and res.data:
        return f"SUCCESS: Event '{event_title or event_id}' deleted."
    return f"ERROR: Failed to delete event '{event_title or event_id}'."
