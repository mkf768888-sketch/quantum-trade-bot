# QuantumTrade AI — Design Concepts

8 standalone HTML design concept files for the Telegram Mini App (375px mobile viewport).
All files use static fake data, dark theme, CSS-only animations, no external CDN dependencies.

---

## Concepts

### 1. design-cyberpunk.html — Cyberpunk Neon (Blade Runner 2049)
Dark `#0a0a0f` background with neon purple `#b722ff` and cyan `#00fff7` accents. Space Mono monospace font, thin neon-bordered cards with box-shadow glow. Features a scanline overlay via CSS `repeating-linear-gradient`, glitch animation on the main title, and pulsing PnL numbers. Includes a live data ticker and a signal log with event timestamps.

### 2. design-bloomberg.html — Bloomberg Terminal Pro
Minimal `#0d0d0d` background with amber `#ff9900` accents. Maximum information density with no decorative borders — only thin `#333` line dividers. Monospace right-aligned numbers, colored dot status indicators (●), MiroFish agent grid, and a command-line prompt bar at the bottom. Designed for traders who want data first.

### 3. design-glassmorphism.html — Glassmorphism Galaxy
Animated 8s gradient background cycling through deep blues and purples with `backdrop-filter: blur(20px)` glass cards. CSS star field built from 20+ `radial-gradient` points on pseudo-elements, three floating orb glows, an SVG mini chart, and subtle particle drift animations. Electric blue `#4488ff` and soft purple `#9966ff` accents.

### 4. design-synthwave.html — Synthwave Retro (80s OutRun)
Deep `#120024` background with a CSS perspective grid horizon that scrolls in a loop, and a sunset gradient sun with retro stripe mask. Orbitron Google Font, magenta `#ff006e` + neon yellow `#fbff00` + purple `#7700ff`. Key numbers use the outline text effect via `-webkit-text-stroke` with matching neon `text-shadow`. Pure retro-futurist aesthetic.

### 5. design-minimal-dark.html — Minimal Dark (Linear/Vercel style)
Pure `#111111` background with `#1a1a1a` cards and `#2a2a2a` borders. Inter font, emerald `#00d084` for positive/buy indicators. Large bold PnL numbers for immediate visibility. Includes a TP/SL progress bar showing current position relative to targets. 150ms micro-transitions only — no heavy animations. The most functional and least fatiguing concept for daily use.

### 6. design-matrix.html — Matrix Terminal
Pure black `#000000` with phosphor green `#00ff41` text throughout. Courier New strictly. Box-drawing character ASCII art logo in the header. Lightweight canvas Matrix rain animation (falling Japanese characters + hex digits) at 15% opacity in the background, CRT scanline overlay, and vignette. Negative numbers in `#ff0040`. Full terminal aesthetic with a root prompt bar.

### 7. design-deep-ocean.html — Deep Ocean Bioluminescence
Deep navy `#000814` to `#001233` gradient with bioluminescent cyan `#48cae4` accents. Cards use `backdrop-filter` blur with very dark semi-transparent backgrounds. All positive numbers glow cyan with a slow 3–4s jellyfish breathing pulse animation. Coral `#ff6b6b` for losses. SVG wave dividers between sections, floating CSS particle field, calm and reliable atmosphere.

### 8. design-quantum.html — Quantum Cosmos (Brand Identity)
Deep space `#020010` with a dense CSS star field (25+ `radial-gradient` points on pseudo-elements). Quantum purple `#7c3aed` + gold `#fbbf24` brand colors. Animated atom/orbit logo with three rotating rings and orbital dots built entirely in CSS. Q-Score displayed as a "quantum charge" dial with a conic-gradient arc fill and orbital animation. The most brand-coherent concept.

---

## Recommendation

**Recommended primary UI: design-minimal-dark.html**

Reasoning:

1. **Daily usability.** Telegram Mini App is opened dozens of times per day for quick balance checks and position monitoring. The minimal design reduces cognitive load — numbers are large, hierarchy is clear, nothing competes for attention.

2. **Readability.** Inter font at system rendering, no glow effects on text, pure white/emerald contrast ratios exceed WCAG AA on dark backgrounds. Bloomberg Terminal is similarly readable but more cluttered. Glassmorphism and Deep Ocean degrade at low screen brightness common in dark environments.

3. **Performance.** No canvas, no backdrop-filter blur (which is GPU-heavy on low-end Android phones common among Telegram users), no animated gradients. The only transitions are 150ms ease on hover — this keeps battery drain minimal during extended monitoring sessions.

4. **Professional look.** Matches the visual language of modern fintech apps (Linear, Vercel, Raycast). Signals trustworthiness without the gimmick associations of Matrix or Synthwave. The profit green `#00d084` is immediately readable as positive without needing glow effects.

5. **Scalability.** The flat card system (`#1a1a1a` + `#2a2a2a` border) handles dense data — trade history tables, settings forms, earn product lists — without visual noise. Other concepts would need significant work to accommodate content-heavy screens.

**Second choice: design-quantum.html** — if brand identity matters more than usability. The orbital logo and quantum charge dial are unique and memorable, making the app feel like a distinct product rather than a generic trading tool. With Inter font substituted for the current system-ui and glow animations dialed back by 50%, it would be production-ready.
