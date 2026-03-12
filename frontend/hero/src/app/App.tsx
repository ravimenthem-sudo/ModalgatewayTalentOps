import React from 'react';
import { motion } from 'motion/react';
import Navigation from './components/Navigation';
import ScrollProgress from './components/ScrollProgress';
import Hero from './components/Hero';
import Problem from './components/Problem';
import Services from './components/Services';
import Approach from './components/Approach';
import Industries from './components/Industries';
import Results from './components/Results';
import WhyTalentOps from './components/WhyTalentOps';
import FinalCTA from './components/FinalCTA';
import Footer from './components/Footer';

function App() {
  return (
    <motion.div 
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5 }}
      className="min-h-screen bg-[#f7f7f9]"
    >
      <ScrollProgress />
      <Navigation />
      <Hero />
      <Problem />
      <Services />
      <Approach />
      <Industries />
      <Results />
      <WhyTalentOps />
      <FinalCTA />
      <Footer />
    </motion.div>
  );
}

export default App;
