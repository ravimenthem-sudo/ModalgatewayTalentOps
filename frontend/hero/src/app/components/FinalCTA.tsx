import React from 'react';
import { ArrowRight } from 'lucide-react';
import { motion } from 'motion/react';
import { useInView } from 'motion/react';

export default function FinalCTA() {
  const ref = React.useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.3 });

  return (
    <section id="contact" className="py-32 px-6 lg:px-12 bg-gradient-to-br from-[#121212] to-[#2a2a2a] relative overflow-hidden">
      {/* Grid pattern overlay */}
      <motion.div 
        initial={{ opacity: 0 }}
        animate={{ opacity: 0.05 }}
        transition={{ duration: 1 }}
        className="absolute inset-0"
        style={{
          backgroundImage: `
            linear-gradient(to right, white 1px, transparent 1px),
            linear-gradient(to bottom, white 1px, transparent 1px)
          `,
          backgroundSize: '80px 80px'
        }}
      ></motion.div>

      <motion.div 
        ref={ref}
        initial={{ opacity: 0, y: 40 }}
        animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 40 }}
        transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
        className="relative max-w-4xl mx-auto text-center"
      >
        <h2 className="text-4xl md:text-5xl lg:text-6xl mb-6 text-white tracking-tight leading-tight">
          Bring Structure to Your Growth
        </h2>
        <p className="text-xl md:text-2xl text-white opacity-80 mb-12 leading-relaxed">
          Stop managing talent by instinct. Start building with intention.
        </p>
        
        <motion.button 
          whileHover={{ scale: 1.05, boxShadow: "0 20px 50px rgba(255, 255, 255, 0.2)" }}
          whileTap={{ scale: 0.98 }}
          transition={{ duration: 0.2 }}
          className="group bg-white text-[#121212] px-10 py-5 rounded-xl text-lg flex items-center justify-center gap-3 mx-auto shadow-2xl"
        >
          Book a Strategy Call
          <ArrowRight className="w-6 h-6 group-hover:translate-x-1 transition-transform" />
        </motion.button>

        <motion.p 
          initial={{ opacity: 0 }}
          animate={isInView ? { opacity: 0.6 } : { opacity: 0 }}
          transition={{ delay: 0.4 }}
          className="mt-8 text-white"
        >
          30-minute consultation • No commitment required
        </motion.p>
      </motion.div>

      {/* Decorative accent */}
      <motion.div 
        initial={{ scale: 0, opacity: 0 }}
        animate={{ scale: 1, opacity: 0.1 }}
        transition={{ duration: 1.5, delay: 0.5 }}
        className="absolute top-10 left-10 w-32 h-32 rounded-full bg-[#a5c9ff] blur-3xl"
      ></motion.div>
      <motion.div 
        initial={{ scale: 0, opacity: 0 }}
        animate={{ scale: 1, opacity: 0.1 }}
        transition={{ duration: 1.5, delay: 0.7 }}
        className="absolute bottom-10 right-10 w-32 h-32 rounded-full bg-[#ffe2de] blur-3xl"
      ></motion.div>
    </section>
  );
}
