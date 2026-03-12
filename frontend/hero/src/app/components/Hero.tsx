import React from 'react';
import { ArrowRight } from 'lucide-react';
import { motion, useScroll, useTransform } from 'motion/react';

export default function Hero() {
  const { scrollY } = useScroll();
  const y = useTransform(scrollY, [0, 500], [0, 150]);
  const opacity = useTransform(scrollY, [0, 300], [1, 0]);

  return (
    <section className="relative pt-32 pb-32 px-6 lg:px-12 overflow-hidden">
      {/* Subtle gradient background */}
      <motion.div 
        initial={{ opacity: 0 }}
        animate={{ opacity: 0.4 }}
        transition={{ duration: 1.2 }}
        style={{ y }}
        className="absolute inset-0 bg-gradient-to-br from-[#e3f2fd] via-[#f7f7f9] to-[#ffe2de]"
      ></motion.div>
      
      {/* Grid pattern overlay */}
      <div 
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage: `
            linear-gradient(to right, #121212 1px, transparent 1px),
            linear-gradient(to bottom, #121212 1px, transparent 1px)
          `,
          backgroundSize: '80px 80px'
        }}
      ></div>

      <motion.div 
        style={{ opacity }}
        className="relative max-w-7xl mx-auto"
      >
        <div className="max-w-4xl">
          <motion.h1 
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
            className="text-5xl md:text-6xl lg:text-7xl mb-8 text-[#121212] leading-[1.1] tracking-tight"
          >
            Operational Clarity for Growing Teams
          </motion.h1>
          <motion.p 
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="text-xl md:text-2xl text-[#121212] opacity-70 mb-12 leading-relaxed max-w-3xl"
          >
            We design, structure, and optimize talent operations so organizations can scale without chaos.
          </motion.p>
          
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.4, ease: [0.22, 1, 0.36, 1] }}
            className="flex flex-col sm:flex-row gap-4"
          >
            <motion.button 
              whileHover={{ scale: 1.02, boxShadow: "0 10px 30px rgba(18, 18, 18, 0.15)" }}
              whileTap={{ scale: 0.98 }}
              transition={{ duration: 0.2 }}
              className="group bg-[#121212] text-white px-8 py-4 rounded-lg flex items-center justify-center gap-2 shadow-lg"
            >
              Book a Strategy Call
              <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
            </motion.button>
            <motion.button 
              whileHover={{ scale: 1.02, backgroundColor: "#121212", color: "#ffffff" }}
              whileTap={{ scale: 0.98 }}
              transition={{ duration: 0.2 }}
              className="border-2 border-[#121212] text-[#121212] px-8 py-4 rounded-lg"
            >
              See How It Works
            </motion.button>
          </motion.div>
        </div>

        {/* Abstract structure lines */}
        <motion.div 
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 0.05, scale: 1 }}
          transition={{ duration: 1.5, delay: 0.6 }}
          className="absolute top-20 right-0 w-1/3 h-64 hidden lg:block"
        >
          <svg viewBox="0 0 200 200" className="w-full h-full">
            <line x1="0" y1="0" x2="200" y2="200" stroke="#121212" strokeWidth="1" />
            <line x1="0" y1="100" x2="200" y2="100" stroke="#121212" strokeWidth="1" />
            <line x1="100" y1="0" x2="100" y2="200" stroke="#121212" strokeWidth="1" />
            <circle cx="100" cy="100" r="50" fill="none" stroke="#121212" strokeWidth="1" />
          </svg>
        </motion.div>
      </motion.div>
    </section>
  );
}
