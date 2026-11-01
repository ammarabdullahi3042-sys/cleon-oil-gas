from pathlib import Path
p=Path('build_cleon_profile_pdfs.py')
s=p.read_text(encoding='utf-8')
s=s.replace("logo=Image(str(ASSET/'cleon-logo-dark-background.png'),width=2.45*inch)", "from PIL import Image as PILImage\n logo_path=ASSET/'cleon-logo-dark-background.png'\n logo_w,logo_h=PILImage.open(logo_path).size\n logo=Image(str(logo_path),width=2.45*inch,height=2.45*inch*logo_h/logo_w)")
s=s.replace("hero=Image(str(ASSET/f'oil-and-gas-hero-{flavor.lower()}-blend.png'),width=6.0*inch)", "hero_path=ASSET/f'oil-and-gas-hero-{flavor.lower()}-blend.png'\n hero_w,hero_h=PILImage.open(hero_path).size\n hero=Image(str(hero_path),width=6.0*inch,height=6.0*inch*hero_h/hero_w)")
p.write_text(s,encoding='utf-8')
