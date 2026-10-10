# Vendored from React Bits

These files are copied from <https://github.com/DavidHDev/react-bits> (TypeScript + Tailwind variants) and used under its
"MIT + Commons Clause" licence (see `LICENSE.react-bits.md`): use inside an application/product is allowed, selling the components
themselves is not. Copyright (c) 2026 David Haz.

Used: LightRays, BlurText, ShinyText, LogoLoop, ClickSpark, CountUp, RubberSegment, Dock, Magnet, DecryptedText, SpotlightCard.
Local changes (all commented in the files): ShinyText gained opt-in `sync` (loops phase-locked to one shared clock) `travel` (equal glint path whatever its width) and `edgeFade` (glint fades in/out along its path) props; ClickSpark uses a viewport-sized, idle-free canvas; LightRays caps its pixel density at 1x.
