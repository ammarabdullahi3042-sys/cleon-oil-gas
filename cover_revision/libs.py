for name in ['scipy','skimage','PIL']:
 try:
  m=__import__(name); print(name,getattr(m,'__version__','ok'))
 except Exception as e: print(name,'no')
