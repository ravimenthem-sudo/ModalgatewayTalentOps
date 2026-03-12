import React from 'react';
import { Building2, Target, Brain } from 'lucide-react';
import { motion } from 'motion/react';
import { useInView } from 'motion/react';

const services = [
  {
    icon: Building2,
    title: 'Talent Operations Architecture',
    description: 'We build structured frameworks for talent acquisition, development, and retention—designed to scale with your organization.',
    features: [
      'Role clarity and org design',
      'Hiring process optimization',
      'Onboarding systems',
      'Career progression frameworks'
    ]
  },
  {
    icon: Target,
    title: 'Productivity & Performance Systems',
    description: 'Move from reactive management to proactive strategy with clear metrics, feedback loops, and accountability structures.',
    features: [
      'Performance evaluation design',
      'OKR and goal-setting frameworks',
      'Manager enablement programs',
      'Team productivity audits'
    ]
  },
  {
    icon: Brain,
    title: 'AI-Enabled Operational Insights',
    description: 'Leverage intelligent tools to surface patterns, predict retention risks, and optimize decision-making across your people operations.',
    features: [
      'Predictive analytics dashboards',
      'Retention risk modeling',
      'Talent pipeline forecasting',
      'Performance trend analysis'
    ]
  }
];

function ServiceCard({ service, index }: { service: typeof services[0]; index: number }) {
  const ref = React.useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.3 });
  const Icon = service.icon;

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 50 }}
      animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 50 }}
      transition={{ duration: 0.6, delay: index * 0.2, ease: [0.22, 1, 0.36, 1] }}
      whileHover={{ y: -8, boxShadow: "0 20px 40px rgba(18, 18, 18, 0.1)" }}
      className="p-10 bg-white border border-[#dadada] rounded-xl transition-all cursor-pointer"
    >
      <motion.div 
        whileHover={{ scale: 1.1, rotate: 5 }}
        transition={{ duration: 0.3 }}
        className="w-16 h-16 rounded-xl bg-gradient-to-br from-[#a5c9ff] to-[#e3f2fd] flex items-center justify-center mb-6"
      >
        <Icon className="w-8 h-8 text-[#121212]" />
      </motion.div>
      <h3 className="text-2xl mb-4 text-[#121212]">
        {service.title}
      </h3>
      <p className="text-[#121212] opacity-60 mb-6 leading-relaxed">
        {service.description}
      </p>
      <ul className="space-y-3">
        {service.features.map((feature, idx) => (
          <motion.li 
            key={idx}
            initial={{ opacity: 0, x: -10 }}
            animate={isInView ? { opacity: 1, x: 0 } : { opacity: 0, x: -10 }}
            transition={{ delay: index * 0.2 + 0.3 + idx * 0.1 }}
            className="flex items-start gap-3"
          >
            <div className="w-1.5 h-1.5 rounded-full bg-[#a5c9ff] mt-2 flex-shrink-0"></div>
            <span className="text-[#121212] opacity-70">{feature}</span>
          </motion.li>
        ))}
      </ul>
    </motion.div>
  );
}

export default function Services() {
  const ref = React.useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.2 });

  return (
    <section id="services" className="py-32 px-6 lg:px-12 bg-[#f7f7f9]">
      <div className="max-w-7xl mx-auto">
        <motion.div 
          ref={ref}
          initial={{ opacity: 0, y: 30 }}
          animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 30 }}
          transition={{ duration: 0.6 }}
          className="text-center mb-20"
        >
          <h2 className="text-4xl md:text-5xl mb-4 text-[#121212] tracking-tight">
            What We Do
          </h2>
          <p className="text-xl text-[#121212] opacity-60 max-w-2xl mx-auto">
            Three core services that transform how you build, manage, and scale your teams.
          </p>
        </motion.div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {services.map((service, index) => (
            <ServiceCard key={index} service={service} index={index} />
          ))}
        </div>
      </div>
    </section>
  );
}
