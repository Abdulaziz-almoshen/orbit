# Playbook: Design styles — the selectable palette (provisioned to the Designer)

A library of **67 ready-made style token-systems** the Designer offers the user to choose from. Each `design-styles/<name>.md` is a complete token spec (color, typography, spacing, radius) + guidance. Adapted from **bergside/awesome-design-skills** (MIT) — see `design-styles/LICENSE-awesome-design-skills.txt` and the repo's CREDITS. This is the menu the Designer shows; the *how* (grounding, signature, anti-AI checklist, quality floor) still comes from `design-methodology.md`.

## How the Designer uses this (mandatory)
On any new component / module / screen, the Designer **shortlists 2–4 styles from this catalog that fit the brief**, builds a **standalone HTML prototype of each**, opens them for the user, and the user **picks one** before any production code is written. See `design-methodology.md` → "Style-prototype selection gate". Never skip straight to building one look.

## Families (shortlist from the family that fits the brief)

- **Minimal & clean:** `minimal`, `clean`, `simple`, `flat`, `modern`, `sleek`, `refined`, `impeccable`, `mono`, `spacious`, `contemporary`
- **Bold & raw:** `bold`, `brutalism`, `neobrutalism`, `dramatic`, `expressive`, `energetic`, `vibrant`, `colorful`
- **Tactile & dimensional:** `glassmorphism`, `neumorphism`, `claymorphism`, `skeumorphism`, `gradient`, `perspective`, `immersive`
- **Retro & nostalgic:** `retro`, `vintage`, `riso`, `dithered`, `sega`, `pacman`, `tetris`, `matrix`, `paper`, `sketch`, `doodle`
- **Premium & elegant:** `luxury`, `premium`, `elegant`, `cafe`, `terracotta`, `cosmic`
- **Business & product:** `corporate`, `enterprise`, `professional`, `application`, `dashboard`, `levels`, `material`, `shadcn`, `ant`
- **Editorial & narrative:** `editorial`, `publication`, `storytelling`, `creative`, `artistic`, `fantasy`, `fiction`, `lingo`
- **Futuristic & playful:** `futuristic`, `neon`, `friendly`, `bento`, `agentic`, `claude`, `codex`

## Full catalog (all 67)

| Style | Vibe | Primary | Secondary |
|---|---|---|---|
| `agentic` | Conversational AI-first interface with minimal controls, clear outcomes, and delegated task flows for agentic workflows. | `#FF5701` | `#F6F6F1` |
| `ant` | Structured, enterprise-focused design system emphasizing clarity, consistency, and efficiency for data-dense web appl… | `#1677ff` | `#8B5CF6` |
| `application` | App dashboard with purple-themed aesthetic, top-bar navigation, card-based layouts, and developer-first workflows. | `#9333ea` | `#a855f7` |
| `artistic` | High-contrast, expressive style with creative typography and bold color choices for visually striking interfaces. | `#3B82F6` | `#8B5CF6` |
| `bento` | Modular grid layout with card-like blocks, clear hierarchy, soft spacing, and subtle visual contrast for organized, s… | `#FAD4C0` | `#80A1C1` |
| `bold` | Strong visual presence with heavyweight typography, high-contrast colors, and commanding layouts. | `#0077BC` | `#009866` |
| `brutalism` | Raw, anti-design aesthetic inspired by concrete architecture with unadorned elements, jarring layouts, and functional… | `#DD614C` | `#DAA144` |
| `cafe` | Cozy cafe-inspired interface with warm tones, soft typography, and clean layouts for a relaxed browsing experience. | `#5D4432` | `#E9E3DD` |
| `claude` | Research-journal aesthetic on warm stone with near-black ink, restrained earthy accents, and editorially strict contr… | `#141413` | `#FAF9F6` |
| `claymorphism` | Soft, rounded 3D-like shapes mimicking malleable clay with playful, puffy elements and colorful surfaces. | `#3B82F6` | `#FFFFFF` |
| `clean` | Simplicity-focused design with ample whitespace, legible typography, and a limited color palette to reduce visual clu… | `#3B82F6` | `#8B5CF6` |
| `codex` | Radically minimal blank-canvas interface where black carries structure and typography drives hierarchy. | `#000000` | `#FFFFFF` |
| `colorful` | Vibrant, high-contrast palettes and gradients for engaging, memorable, and modern user experiences. | `#3B82F6` | `#8B5CF6` |
| `contemporary` | Current-era minimalist design with bento grids, dark mode support, and high-performance accessible layouts. | `#C800DF` | `#E60076` |
| `corporate` | Professional, brand-aligned design with structured grids, minimalist layouts, and consistent enterprise patterns. | `#3B82F6` | `#8B5CF6` |
| `cosmic` | Futuristic sci-fi aesthetic with dark themes, vibrant neon accents, and immersive spatial elements. | `#3B82F6` | `#8B5CF6` |
| `creative` | Playful, character-driven design with expressive typography and bold graphics for landing pages and creative projects. | `#3B82F6` | `#8B5CF6` |
| `dashboard` | Dark-themed cloud-platform aesthetic with modular grids, glass-like panels, and strong data hierarchy for productivit… | `#0C5CAB` | `#0a4a8a` |
| `dithered` | Dot-pattern rendering technique that simulates shades with a limited palette for nostalgic, retro, high-contrast visu… | `#3B82F6` | `#8B5CF6` |
| `doodle` | Hand-drawn, sketch-like style with doodles, handwritten fonts, and imperfect lines for a playful, informal feel. | `#49B6E5` | `#263D5B` |
| `dramatic` | High-contrast, theatrical design with bold layouts, immersive visuals, and unconventional compositions that command a… | `#8B5CF6` | `#F43F5E` |
| `editorial` | Magazine-inspired editorial layout with refined serif typography, structured grids, and elegant reading experiences. | `#111111` | `#f1f1f1` |
| `elegant` | Graceful, refined aesthetic with delicate typography, minimal palettes, and polished layouts that exude sophistication. | `#3B82F6` | `#8B5CF6` |
| `energetic` | Dynamic, vibrant style with thick borders, geometric shapes, high-contrast colors, and expressive typography conveyin… | `#EA580B` | `#F59E0B` |
| `enterprise` | Clean, high-contrast enterprise design for data-driven workflows with intuitive drag-and-drop patterns and structured… | `#072C2C` | `#FF5F03` |
| `expressive` | Vibrant, personality-driven design with bold colors, playful graphics, and dynamic layouts that balance creativity wi… | `#db2777` | `#2563eb` |
| `fantasy` | Game-inspired fantasy aesthetic with bold, premium visuals, rich color palettes, and immersive thematic elements. | `#0250CC` | `#FDC800` |
| `fiction` | Playful, storybook-inspired interface with warm surfaces, chunky outlines, and expressive display typography. | `#222222` | `#FFE9CE` |
| `flat` | Two-dimensional minimalist style with vibrant colors, clean typography, and no 3D effects for fast, user-friendly int… | `#F2673C` | `#8B5CF6` |
| `friendly` | Approachable, intuitive design with rounded elements, ample whitespace, and soft pastel color palettes. | `#F2D9DC` | `#D9F2D8` |
| `futuristic` | Forward-looking design with tech-inspired typography, modern layouts, and a sleek, innovation-driven aesthetic. | `#3B82F6` | `#8B5CF6` |
| `glassmorphism` | Frosted glass effect with translucent layers, subtle blur, and luminous borders for depth and modern elegance. | `#1856FF` | `#3A344E` |
| `gradient` | Smooth color transitions and gradient-rich surfaces for modern, playful interfaces with visual depth. | `#990FFA` | `#E60076` |
| `immersive` | Exhibit-style interface that blends storytelling and game-like interaction on a continuous deep-green canvas. | `#00592B` | `#0023D1` |
| `impeccable` | Graphic editorial-poster aesthetic with warm cream and burnt-orange rhythm plus a sharp amber accent. | `#CC8800` | `#C55221` |
| `levels` | Conversion-focused design that removes friction and guides users toward action through clarity, trust, and speed. | `#27272A` | `#8B5CF6` |
| `lingo` | Playful, minimal design with bright colors, rounded shapes, tactile 3D borders, and friendly illustrations for approa… | `#58cc02` | `#ce82ff` |
| `luxury` | High-end dark aesthetic with bold headings, monochromatic palette, and premium feel for luxury brand experiences. | `#FAFAFA` | `#FAFAFA` |
| `material` | Google's Material Design with layered surfaces, dynamic theming, built-in motion, and responsive cross-platform patte… | `#6442D6` | `#C8B3FD` |
| `matrix` | Dark cyber-terminal visual language with mono typography, dense data layouts, and one green interaction accent. | `#2DB58A` | `#0B0C14` |
| `minimal` | Stripped-back design emphasizing whitespace, clean typography, and restrained color for maximum clarity and focus. | `#0C0C09` | `#312C85` |
| `modern` | Contemporary editorial style with serif typography, minimal palettes, and clean layouts for polished digital products. | `#553F83` | `#111111` |
| `mono` | Monospace-driven, matrix-inspired design with high-contrast elements, compact density, and a hacker-chic aesthetic. | `#37F712` | `#00A6F4` |
| `neobrutalism` | Modern take on brutalism with bold borders, vivid accent colors, and raw, high-contrast layouts on warm surfaces. | `#FDC800` | `#432DD7` |
| `neon` | Electric neon glow effects with high-contrast color pairings for bold, attention-grabbing interfaces. | `#BBF351` | `#00BCFF` |
| `neumorphism` | Soft, extruded UI elements with inner and outer shadows on monochromatic surfaces for a tactile, embedded look. | `#006666` | `#F1F2F5` |
| `pacman` | Retro arcade-inspired design with pixel fonts, dotted borders, playful high-contrast colors, and 8-bit game aesthetics. | `#2A3FE5` | `#F4B9B0` |
| `paper` | Paper-textured, print-inspired design with minimal colors, clean serif/sans typography, and tactile surface qualities. | `#111111` | `#8B5CF6` |
| `perspective` | Spatial depth design with isometric views, vanishing points, and layered elements that guide attention through 3D-lik… | `#00BD7D` | `#00BD7D` |
| `premium` | Apple-inspired premium aesthetic with precise spacing, modern typography, and a refined, polished visual language. | `#3B82F6` | `#8B5CF6` |
| `professional` | Polished, business-ready design with modern typography, structured layouts, and a trustworthy visual identity. | `#FECE14` | `#000000` |
| `publication` | Print-inspired visual language for books, magazines, and reports with editorial grids and expressive typography. | `#A855F7` | `#0A1829` |
| `refined` | Carefully curated, modern minimal style with elegant serif typography and understated, sophisticated palettes. | `#3B82F6` | `#8B5CF6` |
| `retro` | Throwback design with vintage-inspired typography, high-contrast retro palettes, and nostalgic visual elements. | `#3B82F6` | `#8B5CF6` |
| `riso` | Playful two-color risograph-inspired system with paper-like warmth, vivid pink actions, and bold blue structure. | `#F237A1` | `#2C40A7` |
| `sega` | Arcade-inspired game interface with pixel typography, hard edges, and physically punchy, offset-shadow controls. | `#4502FF` | `#FFDA14` |
| `shadcn` | Shadcn/ui-inspired design with minimal, clean components, monochrome palette, and utility-first patterns. | `#000000` | `#111111` |
| `simple` | Straightforward, no-frills design with clean typography, neutral colors, and intuitive layouts that stay out of the way. | `#3B82F6` | `#8B5CF6` |
| `sketch` | Hand-drawn sketch aesthetic on warm paper with soft teal accents, dashed outlines, and tactile illustrated shadows. | `#1DAD97` | `#F4EDE0` |
| `skeumorphism` | Real-world mimicry with textured surfaces, 3D effects, and familiar physical metaphors for intuitive digital interfaces. | `#FA3C00` | `#F08321` |
| `sleek` | Modern minimalist aesthetic with clean lines, intentional color palette, subtle interactions, and consistent spacing. | `#3B82F6` | `#8B5CF6` |
| `spacious` | Generous whitespace, consistent padding, and grid-based layouts for clean, readable, and breathing interfaces. | `#3B82F6` | `#8B5CF6` |
| `storytelling` | Narrative-driven design using visuals, copy, and interaction to guide users through engaging, emotionally resonant jo… | `#3B82F6` | `#8B5CF6` |
| `terracotta` | Sun-baked, clay-toned editorial system with warm cream surfaces, serif headlines, and a single terracotta accent. | `#C56A3C` | `#F3E9D8` |
| `tetris` | Classic block-game inspired design with playful colors, bold display fonts, and compact, high-energy layouts. | `#1C202B` | `#7107E7` |
| `vibrant` | Lively, colorful design with bold playful typography, warm accents, and dynamic visual energy. | `#7C61D4` | `#EAAE87` |
| `vintage` | 1950s-1990s nostalgia with skeuomorphic touches, grainy textures, retro color palettes, and pixel-style typography. | `#008080` | `#C0C0C0` |
