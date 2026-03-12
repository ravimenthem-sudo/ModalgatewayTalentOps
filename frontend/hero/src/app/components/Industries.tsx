import React from 'react';
import { Briefcase, GraduationCap, Rocket, Globe } from 'lucide-react';
import { motion } from 'motion/react';
import { useInView } from 'motion/react';

const industries = [
  {
    icon: Briefcase,
    title: 'Services Companies',
    description: 'Professional services, agencies, and consulting firms navigating rapid team expansion.'
  },
  {
    icon: GraduationCap,
    title: 'Education Institutions',
    description: 'Universities, training organizations, and ed-tech platforms scaling faculty and staff.'
  },
  {
    icon: Rocket,
    title: 'Growing Startups',
    description: 'High-growth ventures moving from scrappy to structured in their talent approach.'
  },
  {
    icon: Globe,
    title: 'Distributed Teams',
    description: 'Remote-first organizations building cohesion across geographies and time zones.'
  }
];

function IndustryCard({ industry, index }: { industry: typeof industries[0]; index: number }) {
  const ref = React.useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.4 });
  const Icon = industry.icon;

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 40 }}
      animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 40 }}
      transition={{ duration: 0.5, delay: index * 0.1, ease: [0.22, 1, 0.36, 1] }}
      whileHover={{ y: -8, boxShadow: "0 20px 35px rgba(18, 18, 18, 0.1)" }}
      className="p-8 bg-white border border-[#dadada] rounded-xl transition-all text-center group cursor-pointer"
    >
      <motion.div 
        whileHover={{ scale: 1.1, rotate: 5 }}
        transition={{ duration: 0.3 }}
        className="w-16 h-16 rounded-full bg-[#e3f2fd] flex items-center justify-center mx-auto mb-4 group-hover:bg-gradient-to-br group-hover:from-[#a5c9ff] group-hover:to-[#e3f2fd] transition-all"
      >
        <Icon className="w-8 h-8 text-[#121212]" />
      </motion.div>
      <h3 className="text-xl mb-3 text-[#121212]">
        {industry.title}
      </h3>
      <p className="text-[#121212] opacity-60 leading-relaxed">
        {industry.description}
      </p>
    </motion.div>
  );
}

export default function Industries() {
  const ref = React.useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.2 });

  return (
    <section id="industries" className="py-32 px-6 lg:px-12 bg-[#f7f7f9]">
      <div className="max-w-7xl mx-auto">
        <motion.div 
          ref={ref}
          initial={{ opacity: 0, y: 30 }}
          animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 30 }}
          transition={{ duration: 0.6 }}
          className="text-center mb-20"
        >
          <h2 className="text-4xl md:text-5xl mb-4 text-[#121212] tracking-tight">
            Industries We Serve
          </h2>
          <p className="text-xl text-[#121212] opacity-60 max-w-2xl mx-auto">
            Tailored expertise for organizations with distinct talent challenges.
          </p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {industries.map((industry, index) => (
            <IndustryCard key={index} industry={industry} index={index} />
          ))}
        </div>
      </div>
    </section>
  );
}
