# Gemini 贴图提示词

用法：在本机 Gemini（图像生成）里，把 **通用前缀** + 各材质的提示词一起发送。生成后按原文件名覆盖 `Textures/T_<Name>_BaseColor.png`，分辨率保持表中数值（正方形，无缝平铺）。

**通用前缀（每条都加）**

> Seamless tileable texture, orthographic top-down flat scan, even diffuse lighting, no shadows, no highlights, no perspective, no vignette, stylized cozy hand-painted 3D game look, soft muted warm palette, albedo only (no baked lighting). Square image.

| 文件 (T_*_BaseColor.png) | 分辨率 | 覆盖尺寸 | 提示词 |
|---|---|---|---|
| Wallpaper_Sage | 1024 | 1 m | Vintage sage-green wallpaper, 4 vertical stripes alternating two close green tones (#7f957f / #89a088) separated by thin darker pinstripes, small pale diamond outline motifs in the lighter stripes, two rows per tile, subtle paper grain |
| Plaster_Lilac | 512 | 1 m | Smooth exterior plaster painted dusty grey-lilac (#8a8398), soft mottling, very fine sand grain |
| Trim_Cream | 512 | 1 m | Cream painted wood trim (#e8d6bc), faint horizontal wood grain under the paint |
| Floor_Checker | 1024 | 1 m | Exactly 4×4 checkerboard of square ceramic tiles, alternating muted raspberry red (#9e4550) and warm cream (#eee0cf), thin dark grout lines, slight per-tile color variation, light wear |
| Floor_PlankGrey | 1024 | 1 m | Exactly 5 horizontal grey-washed wooden floor boards (#9a9aa2), staggered butt joints, soft grain, dark gaps between boards |
| Stone_Foundation | 512 | 1 m | Grey-lilac cut stone blocks in running bond, 2 rows per tile, soft rounded edges, dark mortar |
| Wood_Oak | 1024 | 1 m | Warm orange oak wood (#c07a40), straight horizontal grain running left-right, gentle growth rings |
| Wood_Walnut | 512 | 1 m | Reddish-brown walnut wood (#8a4a36), straight horizontal grain |
| Wood_Crate | 512 | 0.5 m | 4 rough pine crate planks stacked horizontally (#c89a60), visible gaps, raw sawn texture |
| Paint_Sage | 256 | 0.5 m | Sage green painted wood (#8e9a6c), brush strokes following horizontal grain |
| Paint_Brick | 256 | 0.5 m | Brick red painted wood (#a0503e), brush strokes following horizontal grain |
| Counter_Maroon | 256 | 1 m | Matte maroon laminate countertop (#86384a), almost flat with tiny speckles |
| Metal_Steel | 256 | 0.5 m | Brushed stainless steel, fine horizontal brushing lines, light grey |
| Metal_Copper | 256 | 0.5 m | Polished copper (#c26a3a), faint horizontal brushing |
| Metal_Iron | 256 | 0.5 m | Dark cast iron (#35353c), subtle speckle |
| Ceramic_White / Enamel_Cream | 256 | 0.5 m | Glazed off-white ceramic / cream enamel, nearly uniform |
| Glass_Clear | 128 | 0.5 m | Very pale blue-green uniform tint |
| Fabric_Curtain | 512 | 0.5 m | Blue-grey linen weave (#8f969c), visible warp and weft |
| Fabric_LinenWhite / Fabric_Charcoal | 256 | 0.5 m | Off-white / charcoal-navy linen weave |
| Rug_Runner | 256×1024 | whole rug | Long runner rug top view, muted rose-red (#a8505a) wool, a thin light pink inner border line near the edges, darker outer edge, **not tileable**, portrait 1:4 |
| Burlap | 512 | 0.5 m | Coarse burlap sack weave (#b8a078) |
| Wicker | 512 | 0.5 m | Woven wicker basket pattern (#b07c48), tight basket weave |
| Cardboard | 512 | 1 m | Brown corrugated cardboard surface (#c9a06a), soft fibers, faint stains |
| Tape_Kraft | 128 | 0.5 m | Kraft paper packing tape, light tan |
| Bread_Crust | 512 | 0.3 m | Golden baked bread crust (#c88a48), small pores and flour dusting |
| Leaf_Green | 256 | 0.3 m | Fresh herb leaf surface, medium green with faint veins |
| Terracotta | 256 | 0.5 m | Unglazed terracotta clay (#b8603c) |
| Soil_Dark | 128 | 0.3 m | Dark potting soil |
| Paper_Cream | 256 | 0.5 m | Plain cream paper |
| Calendar_Print | 384×512 | whole | Wall calendar page: lilac header band on top, 7×5 grid of empty day boxes below, two binder rings at the top, **not tileable** |
| Note_Paper | 256 | whole | Small yellow sticky note with 6 hand-drawn grey lines, **not tileable** |
| Preserve_Berry / Plum / Pickle / Honey | 128 | 0.3 m | Jam seen through glass: deep berry red / plum purple / olive pickle green / amber honey, soft blotches |
| Plastic_Red / Plastic_Yellow | 128 | 0.3 m | Glossy squeeze-bottle plastic, ketchup red / mustard yellow |
| Paint_Lavender / Paint_Teal | 128 | 0.3 m | Flat painted metal lids / tin labels, lavender / muted teal |

**Normal / ORM**：Gemini 只负责颜色。需要重新配套法线与 ORM 时，可以把新的 BaseColor 丢进 Materialize / Substance Sampler / Photoshop 生成；ORM 通道顺序为 R=AO、G=Roughness、B=Metallic。
