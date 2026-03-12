import React from 'react';
import { AlertCircle, Users, BarChart3, TrendingDown, Workflow } from 'lucide-react';
import { motion } from 'motion/react';
import { useInView } from 'motion/react';

const painPoints = [
  {
    icon: AlertCircle,
    title: 'No Clear Accountability',
    description: 'Roles blur. Ownership gaps emerge. Projects slow down.'
  },
  {
    icon: Users,
    title: 'Scattered Talent Processes',
    description: 'Hiring, onboarding, and performance reviews lack cohesion.'
  },
  {
    icon: BarChart3,
    title: 'Invisible Performance Gaps',
    description: 'Without data, you\'re managing on instinct instead of insight.'
  },
  {
    icon: TrendingDown,
    title: 'Retention Becomes Reactive',
    description: 'You lose your best people before you know why.'
  },
  {
    icon: Workflow,
    title: 'Operational Debt Accumulates',
    description: 'Quick fixes compound. Structure erodes. Teams feel the strain.'
  }
];

function PainPointCard({ point, index }: { point: typeof painPoints[0]; index: number }) {
  const ref = React.useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.4 });
  const Icon = point.icon;

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 40 }}
      animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 40 }}
      transition={{ duration: 0.5, delay: index * 0.1, ease: [0.22, 1, 0.36, 1] }}
      whileHover={{ y: -5, boxShadow: "0 15px 30px rgba(18, 18, 18, 0.08)" }}
      className="p-8 border border-[#dadada] rounded-xl transition-all bg-white cursor-pointer"
    >
      <motion.div 
        whileHover={{ scale: 1.1 }}
        transition={{ duration: 0.2 }}
        className="w-12 h-12 rounded-full bg-[#e3f2fd] flex items-center justify-center mb-4"
      >
        <Icon className="w-6 h-6 text-[#121212]" />
      </motion.div>
      <h3 className="text-xl mb-3 text-[#121212]">
        {point.title}
      </h3>
      <p className="text-[#121212] opacity-60 leading-relaxed">
        {point.description}
      </p>
    </motion.div>
  );
}

export default function Problem() {
  const ref = React.useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.2 });

  return (
    <section className="py-32 px-6 lg:px-12 bg-white">
      <div className="max-w-7xl mx-auto">
        <motion.div 
          ref={ref}
          initial={{ opacity: 0, y: 30 }}
          animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 30 }}
          transition={{ duration: 0.6 }}
          className="text-center mb-20"
        >
          <h2 className="text-4xl md:text-5xl mb-4 text-[#121212] tracking-tight">
            Scaling Creates Invisible Friction
          </h2>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {painPoints.map((point, index) => (
            <PainPointCard key={index} point={point} index={index} />
          ))}
        </div>
      </div>
    </section>
  );
}
