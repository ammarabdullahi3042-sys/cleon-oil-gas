from PIL import Image,ImageDraw
import numpy as np
im=Image.open('cover_revision/extracted0.png').convert('RGB'); a=np.array(im); h,w=a.shape[:2]
mask=np.zeros((h,w),bool)
# Model's display wordmark (bright CLEON palette red) and two white copy lines.
R,G,B=a[:,:,0],a[:,:,1],a[:,:,2]
mask[1380:1515,150:370]=(R[1380:1515,150:370]>165)&(G[1380:1515,150:370]<90)&(B[1380:1515,150:370]<105)&((R[1380:1515,150:370]-G[1380:1515,150:370])>95)
roi=(R[1410:1515,350:1100]>185)&(G[1410:1515,350:1100]>185)&(B[1410:1515,350:1100]>175)&((np.maximum(np.maximum(R[1410:1515,350:1100],G[1410:1515,350:1100]),B[1410:1515,350:1100])-np.minimum(np.minimum(R[1410:1515,350:1100],G[1410:1515,350:1100]),B[1410:1515,350:1100]))<55)
mask[1410:1515,350:1100]=roi
out=Image.new('RGBA',im.size,(0,0,0,0)); pix=np.zeros((h,w,4),dtype=np.uint8); pix[mask]=[255,0,0,180]; out=Image.alpha_composite(im.convert('RGBA'),Image.fromarray(pix)); out.save('cover_revision/model-mask-preview.png')
print('mask pixels',mask.sum())
