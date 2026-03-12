"use client";
import { cn } from "@/lib/utils";
import React, { useEffect, useRef, useState } from "react";
import { createNoise3D } from "simplex-noise";

export const WavyBackground = ({
    children,
    className,
    containerClassName,
    colors,
    waveWidth,
    backgroundFill,
    blur = 10,
    speed = "fast",
    waveOpacity = 0.5,
    ...props
}: {
    children?: any;
    className?: string;
    containerClassName?: string;
    colors?: string[];
    waveWidth?: number;
    backgroundFill?: string;
    blur?: number;
    speed?: "slow" | "fast";
    waveOpacity?: number;
    [key: string]: any;
}) => {
    const noise = createNoise3D();
    let w: number,
        h: number,
        nt: number,
        i: number,
        x: number,
        ctx: any,
        canvas: any;
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const animationFrameRef = useRef<number>();

    // Quality multiplier for downsampling (0.5 means half resolution)
    const dpr = typeof window !== 'undefined' ? window.devicePixelRatio : 1;
    const qualityMultiplier = 0.5;

    const getSpeed = () => {
        switch (speed) {
            case "slow":
                return 0.001;
            case "fast":
                return 0.002;
            default:
                return 0.001;
        }
    };

    const isVisibleRef = useRef(true);

    useEffect(() => {
        const observer = new IntersectionObserver(
            ([entry]) => {
                isVisibleRef.current = entry.isIntersecting;
            },
            { threshold: 0.05 }
        );
        if (canvasRef.current) observer.observe(canvasRef.current);
        return () => observer.disconnect();
    }, []);

    const init = () => {
        canvas = canvasRef.current;
        if (!canvas) return;
        ctx = canvas.getContext("2d", { alpha: false, desynchronized: true });

        const updateDimensions = () => {
            w = ctx.canvas.width = window.innerWidth * qualityMultiplier;
            h = ctx.canvas.height = window.innerHeight * qualityMultiplier;
            // No need for ctx.filter, we use CSS blur for better performance
            nt = 0;
        };

        updateDimensions();

        let resizeTimeout: any;
        window.addEventListener('resize', () => {
            if (resizeTimeout) clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(updateDimensions, 150);
        });

        render();
    };

    const waveColors = colors ?? [
        "#ffffff",
        "#cccccc",
        "#999999",
        "#666666",
        "#333333",
    ];

    const drawWave = (n: number) => {
        nt += getSpeed();
        for (i = 0; i < n; i++) {
            ctx.beginPath();
            ctx.lineWidth = (waveWidth || 50) * qualityMultiplier;
            ctx.strokeStyle = waveColors[i % waveColors.length];
            for (x = 0; x < w; x += 10) { // Increased step for performance
                var y = noise(x / (400 * qualityMultiplier), 0.3 * i, nt) * (50 * qualityMultiplier);
                ctx.lineTo(x, y + h * 0.5);
            }
            ctx.stroke();
            ctx.closePath();
        }
    };

    const render = () => {
        if (!isVisibleRef.current) {
            animationFrameRef.current = requestAnimationFrame(render);
            return;
        }

        ctx.fillStyle = backgroundFill || "black";
        ctx.globalAlpha = 1.0; // Avoid globalAlpha if possible for drawing background
        ctx.fillRect(0, 0, w, h);

        ctx.globalAlpha = waveOpacity || 0.5;
        drawWave(4); // Reduced wave count slightly

        animationFrameRef.current = requestAnimationFrame(render);
    };

    useEffect(() => {
        init();
        return () => {
            if (animationFrameRef.current) {
                cancelAnimationFrame(animationFrameRef.current);
            }
        };
    }, []);

    return (
        <div
            className={cn(
                "flex flex-col items-center justify-center bg-black",
                containerClassName
            )}
        >
            <canvas
                className="absolute inset-0 z-0 w-full h-full"
                ref={canvasRef}
                id="canvas"
                style={{
                    filter: `blur(${blur}px)`,
                    transform: 'scale(1.05)', // Prevent blur edges from showing
                    imageRendering: 'auto',
                }}
            ></canvas>
            <div className={cn("relative z-10", className)} {...props}>
                {children}
            </div>
        </div>
    );
};
