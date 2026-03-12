import React, { Suspense, lazy, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useLocation } from 'react-router-dom';
import { StylesInjection } from './styles/StylesInjection';
import { Navigation } from './components/Navigation';
import { SmoothScroll } from './components/SmoothScroll';

// Lazy load sections for optimized performance
const HeroSection = lazy(() => import('./sections/HeroSection').then(m => ({ default: m.HeroSection })));
const Problem = lazy(() => import('./sections/Problem'));
const Services = lazy(() => import('./sections/Services'));
const Approach = lazy(() => import('./sections/Approach'));
const Industries = lazy(() => import('./sections/Industries'));
const Foundations = lazy(() => import('./sections/Foundations'));
const Results = lazy(() => import('./sections/Results'));
const WhyTalentOps = lazy(() => import('./sections/WhyTalentOps'));
const PricingSummary = lazy(() => import('./sections/PricingSummary'));
const FinalCTA = lazy(() => import('./sections/FinalCTA'));
const Footer = lazy(() => import('./sections/Footer'));
const ScrollProgress = lazy(() => import('./sections/ScrollProgress'));

const LoadingSection = () => <div className="min-h-screen bg-[#f7f7f9]" />;

export function LandingPage() {
    const location = useLocation();
    const scrollTo = (location.state as any)?.scrollTo;

    useEffect(() => {
        if (scrollTo) {
            // Clear the state so refresh doesn't re-scroll
            window.history.replaceState({}, '');

            // Poll for the element and scroll instantly (before fade-in completes)
            let cancelled = false;
            const tryScroll = () => {
                if (cancelled) return;
                const el = document.getElementById(scrollTo);
                if (el) {
                    el.scrollIntoView({ behavior: 'instant' as ScrollBehavior, block: 'start' });
                } else {
                    requestAnimationFrame(tryScroll);
                }
            };
            requestAnimationFrame(tryScroll);

            // Safety timeout to stop polling after 2s
            const timeout = setTimeout(() => { cancelled = true; }, 2000);
            return () => { cancelled = true; clearTimeout(timeout); };
        }
    }, [scrollTo]);
    return (
        <SmoothScroll>
            <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.5 }}
                className="relative w-full bg-[#f7f7f9] text-[#1f2937] font-sans selection:bg-[#a5c9ff] selection:text-[#1f2937]"
            >
                <Suspense fallback={null}>
                    <ScrollProgress />
                </Suspense>

                <main className="overflow-x-hidden">
                    <Suspense fallback={<LoadingSection />}>
                        <div className="gpu-accel">
                            <HeroSection />
                        </div>
                    </Suspense>

                    <Suspense fallback={null}>
                        <div style={{ contentVisibility: 'auto', containIntrinsicSize: '0 500px' }} className="gpu-accel">
                            <Problem />
                        </div>
                        <div style={{ contentVisibility: 'auto', containIntrinsicSize: '0 800px' }} className="gpu-accel">
                            <Services />
                        </div>
                        <div style={{ contentVisibility: 'auto', containIntrinsicSize: '0 100vh' }} className="gpu-accel">
                            <Approach />
                        </div>
                        <div style={{ contentVisibility: 'auto', containIntrinsicSize: '0 600px' }} className="gpu-accel">
                            <Industries />
                        </div>
                        <div style={{ contentVisibility: 'auto', containIntrinsicSize: '0 800px' }} className="gpu-accel">
                            <Foundations />
                        </div>
                        <div style={{ contentVisibility: 'auto', containIntrinsicSize: '0 600px' }} className="gpu-accel">
                            <Results />
                        </div>
                        <div style={{ contentVisibility: 'auto', containIntrinsicSize: '0 500px' }} className="gpu-accel">
                            <WhyTalentOps />
                        </div>
                        <div style={{ contentVisibility: 'auto', containIntrinsicSize: '0 500px' }} className="gpu-accel">
                            <PricingSummary />
                        </div>
                        <div style={{ contentVisibility: 'auto', containIntrinsicSize: '0 400px' }} className="gpu-accel">
                            <FinalCTA />
                        </div>
                    </Suspense>
                </main>

                <Suspense fallback={null}>
                    <Footer />
                </Suspense>
            </motion.div>
        </SmoothScroll>
    );
}
