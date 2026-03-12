import { useEffect } from 'react'

const STYLES = `
/* --- GLOBAL CSS --- */
:root {
  --font-inter: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;

  /* Theme Variables - New Minimal Palette */
  --bg-base: #f7f7f9;
  --accent-primary: #a5c9ff;
  --bg-soft: #e3f2fd;
  --accent-secondary: #ffe2de;
  --color-border: #dadada;
  --text-dark: #1f2937;
  --cta-blue: #3b82f6;
  --cta-dark: #2563eb;

  /* Fonts */
  --font-playfair: 'Playfair Display', serif;
  --font-cormorant: 'Cormorant Garamond', serif;
  --font-space: 'Space Grotesk', sans-serif;
  --font-redhat: 'Red Hat Display', sans-serif;
  --font-leckerli: 'Leckerli One', cursive;
  --font-satisfy: 'Satisfy', cursive;
}

.font-redhat { font-family: var(--font-redhat); }
.font-leckerli { font-family: var(--font-leckerli); }
.font-satisfy { font-family: var(--font-satisfy); }

/* Base Utility Overrides */
.reveal-fade { opacity: 0; visibility: hidden; }

html.lenis, html.lenis body { height: auto; }
.lenis.lenis-smooth { scroll-behavior: auto !important; }
.lenis.lenis-stopped { overflow: hidden; }

/* Performance optimization for smooth scrolling */
body {
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* Enable hardware acceleration for fixed backgrounds or large sections if needed */
.gpu-accel {
  transform: translateZ(0);
  will-change: transform;
}
`

export const StylesInjection = () => {
  useEffect(() => {
    // Inject Optimized Fonts
    const linkId = 'talentops-fonts'
    if (!document.getElementById(linkId)) {
      const link = document.createElement('link')
      link.id = linkId
      // Optimized font string: reduced weights and added swap
      link.href = "https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600;700&family=Inter:wght@400;500;600;700&family=Playfair+Display:wght@400;700&family=Red+Hat+Display:wght@400;700&family=Space+Grotesk:wght@400;700&display=swap"
      link.rel = "stylesheet"
      document.head.appendChild(link)
    }

    // Inject Styles
    const styleId = 'talentops-minimal-styles'
    if (!document.getElementById(styleId)) {
      const style = document.createElement('style')
      style.id = styleId
      style.innerHTML = STYLES
      document.head.appendChild(style)
    }
  }, [])
  return null
}
