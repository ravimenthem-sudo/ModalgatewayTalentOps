# Landing Page Sections Structure

This document lists the sections currently included in the `LandingPage.tsx` component, in the order they appear.

## Main Content Sections

These sections render sequentially within the `<main>` tag:

1.  **HeroSection**
    *   **Component:** `<HeroSection />`
    *   **Path:** `./sections/HeroSection`
    *   **Description:** The initial view of the landing page (Hero).

2.  **Problem**
    *   **Component:** `<Problem />`
    *   **Path:** `./sections/Problem`
    *   **Description:** likely describes the problem the product solves.

3.  **Services**
    *   **Component:** `<Services />`
    *   **Path:** `./sections/Services`
    *   **Description:** Lists services offered.

4.  **Approach**
    *   **Component:** `<Approach />`
    *   **Path:** `./sections/Approach`
    *   **Description:** Explains the methodology or approach.

5.  **Industries**
    *   **Component:** `<Industries />`
    *   **Path:** `./sections/Industries`
    *   **Description:** Target industries.

6.  **Results**
    *   **Component:** `<Results />`
    *   **Path:** `./sections/Results`
    *   **Description:** Case studies or outcomes.

7.  **WhyTalentOps**
    *   **Component:** `<WhyTalentOps />`
    *   **Path:** `./sections/WhyTalentOps`
    *   **Description:** Value proposition/Differentiators.

8.  **FinalCTA**
    *   **Component:** `<FinalCTA />`
    *   **Path:** `./sections/FinalCTA`
    *   **Description:** Final Call to Action at the bottom of the main content.

## Layout & Overlay Components

These components provide structure or functionality across the page:

*   **Navigation**
    *   **Component:** `<Navigation />`
    *   **Path:** `./components/Navigation`
    *   **Position:** Fixed/Sticky top (usually).

*   **Footer**
    *   **Component:** `<Footer />`
    *   **Path:** `./sections/Footer`
    *   **Position:** Bottom of the page, outside `<main>`.

*   **ScrollProgress**
    *   **Component:** `<ScrollProgress />`
    *   **Path:** `./sections/ScrollProgress`
    *   **Description:** Visual indicator of scroll position.

*   **SmoothScroll**
    *   **Component:** `<SmoothScroll>`
    *   **Path:** `./components/SmoothScroll`
    *   **Description:** Wrapper for smooth scrolling behavior.
