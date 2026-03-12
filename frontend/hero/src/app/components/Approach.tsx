import React from 'react';
import { Search, PenTool, Hammer, Users, RefreshCw } from 'lucide-react';
import { motion } from 'motion/react';
import { useInView } from 'motion/react';

const steps = [
  {
    icon: Search,
    title: 'Diagnose',
    description: 'We analyze your current state: workflows, gaps, pain points, and goals.'
  },
  {
    icon: PenTool,
    title: 'Design',
    description: 'Custom frameworks built for your team structure, industry, and growth stage.'
  },
  {
    icon: Hammer,
    title: 'Implement',
    description: 'Hands-on deployment with your team, including tools, templates, and training.'
  },
  {
    icon: Users,
    title: 'Align',
    description: 'Manager enablement and team onboarding to ensure adoption and understanding.'
  },
  {
    icon: RefreshCw,
    title: 'Optimize',
    description: 'Ongoing measurement, iteration, and refinement as you scale.'
  }
];

function StepCard({ step, index }: { step: typeof steps[0]; index: number }) {
  const ref = React.useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.4 });
  const Icon = step.icon;

  return (
    <div className="relative">
      <motion.div
        ref={ref}
        initial={{ opacity: 0, y: 50 }}
        animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 50 }}
        transition={{ duration: 0.5, delay: index * 0.15, ease: [0.22, 1, 0.36, 1] }}
        whileHover={{ y: -8, boxShadow: "0 15px 30px rgba(18, 18, 18, 0.08)" }}
        className="text-center p-6 rounded-xl border border-[#dadada] bg-[#f7f7f9] transition-all h-full flex flex-col"
      >
        <motion.div 
          whileHover={{ scale: 1.15, rotate: 10 }}
          transition={{ duration: 0.3 }}
          className="w-14 h-14 rounded-full bg-gradient-to-br from-[#a5c9ff] to-[#e3f2fd] flex items-center justify-center mx-auto mb-4"
        >
          <Icon className="w-7 h-7 text-[#121212]" />
        </motion.div>
        <h3 className="text-xl mb-3 text-[#121212]">
          {step.title}
        </h3>
        <p className="text-sm text-[#121212] opacity-60 leading-relaxed flex-grow">
          {step.description}
        </p>
        <motion.div 
          initial={{ opacity: 0 }}
          animate={isInView ? { opacity: 1 } : { opacity: 0 }}
          transition={{ delay: index * 0.15 + 0.3 }}
          className="mt-4 text-xs text-[#a5c9ff] tracking-widest"
        >
          STEP {index + 1}
        </motion.div>
      </motion.div>
      
      {/* Connector arrow for desktop */}
      {index < steps.length - 1 && (
        <motion.div 
          initial={{ scaleX: 0 }}
          animate={isInView ? { scaleX: 1 } : { scaleX: 0 }}
          transition={{ delay: index * 0.15 + 0.4, duration: 0.4 }}
          className="hidden md:block absolute top-1/2 -right-3 transform -translate-y-1/2 z-10 origin-left"
        >
          <div className="w-6 h-0.5 bg-[#dadada]"></div>
        </motion.div>
      )}
    </div>
  );
}

export default function Approach() {
  const ref = React.useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.2 });

  return (
    <section id="approach" className="py-32 px-6 lg:px-12 bg-white">
      <div className="max-w-7xl mx-auto">
        <motion.div 
          ref={ref}
          initial={{ opacity: 0, y: 30 }}
          animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 30 }}
          transition={{ duration: 0.6 }}
          className="text-center mb-20"
        >
          <h2 className="text-4xl md:text-5xl mb-4 text-[#121212] tracking-tight">
            How We Work
          </h2>
          <p className="text-xl text-[#121212] opacity-60 max-w-2xl mx-auto">
            A structured, repeatable process that brings clarity to complexity.
          </p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-5 gap-6">
          {steps.map((step, index) => (
            <StepCard key={index} step={step} index={index} />
          ))}
        </div>
      </div>
    </section>
  );
}
