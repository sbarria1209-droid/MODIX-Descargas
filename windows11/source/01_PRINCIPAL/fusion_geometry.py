"""Geometría multicámara: reproyección de capa y exclusión de oclusores 3D."""
from __future__ import annotations
import math
import cv2
import numpy as np

class CalibrationError(ValueError):pass

def _normalize(points):
    points=np.asarray(points,dtype=np.float64);dim=points.shape[1];center=points.mean(0);distance=np.linalg.norm(points-center,axis=1).mean()
    if distance<1e-9:raise CalibrationError('Las referencias deben estar separadas')
    scale=math.sqrt(dim)/distance;T=np.eye(dim+1);T[:dim,:dim]*=scale;T[:dim,dim]=-center*scale
    return (points-center)*scale,T

def world_references(reference):
    x,y,w,d,z0,z1=[float(reference[k]) for k in ('x','y','width','depth','z0','z1')]
    if min(w,d)<20 or abs(z1-z0)<20:raise CalibrationError('Usa un rectángulo y dos alturas separados al menos 20 mm')
    return np.asarray([[a,b,z] for z in (z0,z1) for a,b in ((x,y),(x+w,y),(x+w,y+d),(x,y+d))],float)

def fit_projection(world,image_uv,frame_size):
    world=np.asarray(world,dtype=np.float64);uv=np.asarray(image_uv,dtype=np.float64)
    if world.shape!=(8,3) or uv.shape!=(8,2) or not np.isfinite(world).all() or not np.isfinite(uv).all():raise CalibrationError('Marca las ocho referencias de la cámara')
    if np.any(uv<0) or np.any(uv>1):raise CalibrationError('Las referencias deben estar dentro de la imagen')
    for quad in (uv[:4],uv[4:]):
        if abs(cv2.contourArea(quad.astype(np.float32)))<.003 or not cv2.isContourConvex(quad.astype(np.float32)):raise CalibrationError('Marca las cuatro esquinas en orden: X−Y−, X+Y−, X+Y+, X−Y+')
    xyz,T=_normalize(world);xy,U=_normalize(uv);A=[]
    for point,(u,v) in zip(xyz,xy):
        X=np.r_[point,1.];A.append(np.r_[X,np.zeros(4),-u*X]);A.append(np.r_[np.zeros(4),X,-v*X])
    _,singular,V=np.linalg.svd(np.asarray(A))
    if singular[-2]<1e-8:raise CalibrationError('Referencias degeneradas; comprueba las dos alturas y el orden')
    P=np.linalg.inv(U)@V[-1].reshape(3,4)@T;depth=(P@np.c_[world,np.ones(8)].T)[2]
    if depth.mean()<0:P=-P;depth=-depth
    if np.any(depth<=0):raise CalibrationError('Referencias incompatibles o fuera del campo de la cámara')
    P/=np.linalg.norm(P[2,:3]);pred=project(P,world);pixels=(pred-uv)*np.asarray(frame_size,float);rms=float(np.sqrt(np.mean(np.sum(pixels*pixels,axis=1))))
    if not np.isfinite(rms) or rms>6:raise CalibrationError(f'Error de ajuste {rms:.1f} px; vuelve a marcar las referencias (máximo 6 px)')
    return P,rms

def project(P,points):
    points=np.atleast_2d(np.asarray(points,dtype=np.float64));q=(np.asarray(P)@np.c_[points,np.ones(len(points))].T).T
    return np.divide(q[:,:2],q[:,2:3],out=np.full((len(points),2),np.nan),where=np.abs(q[:,2:3])>1e-9)

def plane_height(camera,z,kinematics):
    return float((camera.get('calibration') or {}).get('machine_z',0)) if kinematics=='bed_moves' else float(z)

def mapping(P,z,bed,canvas,source_size):
    width,height=canvas;sw,sh=source_size;x0,y0,bw,bd=[float(bed[k]) for k in ('x','y','width','depth')]
    world=np.array([[bw/max(1,width-1),0,x0],[0,-bd/max(1,height-1),y0+bd],[0,0,1]],float)
    H=np.column_stack((P[:,0],P[:,1],P[:,2]*float(z)+P[:,3]))@world
    yy,xx=np.indices((height,width),dtype=np.float32);den=H[2,0]*xx+H[2,1]*yy+H[2,2]
    with np.errstate(divide='ignore',invalid='ignore'):
        mx=(H[0,0]*xx+H[0,1]*yy+H[0,2])/den*(sw-1);my=(H[1,0]*xx+H[1,1]*yy+H[1,2])/den*(sh-1)
    valid=(den>1e-6)&np.isfinite(mx)&np.isfinite(my)&(mx>=1)&(mx<sw-2)&(my>=1)&(my<sh-2)
    mx=np.where(valid,mx,-1).astype(np.float32);my=np.where(valid,my,-1).astype(np.float32)
    distance=cv2.distanceTransform(valid.astype(np.uint8),cv2.DIST_L2,3);score=np.minimum(distance,40)+1
    return mx,my,valid,score.astype(np.float32)

def cuboid(x0,x1,y0,y1,z0,z1):return np.asarray([[x,y,z] for x in (x0,x1) for y in (y0,y1) for z in (z0,z1)],float)

def occlusion_mask(camera,frame_size,pose,plane,bed,arm):
    width,height=frame_size;mask=np.zeros((height,width),np.uint8);P=np.asarray(camera['calibration']['projection'],float)
    for polygon in camera.get('masks',[]):
        pts=np.asarray(polygon,float)
        if pts.ndim==2 and pts.shape[0]>=3 and pts.shape[1]==2 and np.isfinite(pts).all():cv2.fillPoly(mask,[np.rint(pts*np.array([width-1,height-1])).astype(np.int32)],255)
    if arm.get('enabled',True) and pose is not None:
        x,y,_=pose['xyz'];margin=float(arm.get('margin',20))+float(pose.get('uncertainty',0));radius=float(arm.get('head_radius',40))+margin;head_z=float(arm.get('head_height',130));beam_width=float(arm.get('beam_width',60))/2+margin;beam_bottom=float(arm.get('beam_bottom',35));beam_top=float(arm.get('beam_top',130));axis=arm.get('axis','x')
        boxes=[cuboid(x-radius,x+radius,y-radius,y+radius,plane,plane+head_z)]
        if axis in ('x','both'):boxes.append(cuboid(bed['x'],bed['x']+bed['width'],y-beam_width,y+beam_width,plane+beam_bottom,plane+beam_top))
        if axis in ('y','both'):boxes.append(cuboid(x-beam_width,x+beam_width,bed['y'],bed['y']+bed['depth'],plane+beam_bottom,plane+beam_top))
        for box in boxes:
            q=(P@np.c_[box,np.ones(8)].T).T
            if np.any(q[:,2]<=1e-6):continue
            pixels=q[:,:2]/q[:,2:3]*np.array([width-1,height-1]);pixels=np.clip(pixels,[-4*width,-4*height],[5*width,5*height]);hull=cv2.convexHull(np.rint(pixels).astype(np.int32));cv2.fillConvexPoly(mask,hull,255)
    return mask

class Composer:
    def __init__(self):self.cache={};self.previous=None;self.checker=None;self.labels=[];self.kernel=np.ones((3,3),np.uint8)
    def compose(self,views,config,pose):
        size=int(config.get('canvas',640));bed=config['bed'];height=max(80,round(size*bed['depth']/bed['width']));height=min(1200,height);canvas=(size,height)
        if self.checker is None or self.checker.shape[:2]!=(height,size):
            yy,xx=np.indices((height,size));gray=(((xx//12+yy//12)%2)*25+38).astype(np.uint8);self.checker=cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR);self.labels=[np.full((height,size),i,np.int16) for i in range(8)]
        out=self.checker.copy();best=np.zeros((height,size),np.float32);winner=np.full((height,size),-1,np.int16);scores={};warped={};visible={};contributions={};total=height*size
        for index,(camera,frame,stamp) in enumerate(views):
            calibration=camera.get('calibration') or {};P=np.asarray(calibration.get('projection',[]),float);sw,sh=frame.shape[1],frame.shape[0]
            if P.shape!=(3,4) or not np.isfinite(P).all():continue
            reference_size=calibration.get('frame_size',[sw,sh])
            if [sw,sh]!=list(reference_size):continue
            z=plane_height(camera,pose['xyz'][2],config.get('kinematics','bed_moves'));key=(camera.get('uid',camera['index']),round(z,3),sw,sh,size,height,tuple(P.flatten()),tuple(bed.values()))
            if key not in self.cache:
                if len(self.cache)>24:self.cache.clear()
                mx,my,valid,score=mapping(P,z,bed,canvas,(sw,sh));self.cache[key]=(mx,my,valid.astype(np.uint8)*255,score)
            mx,my,valid,base_score=self.cache[key];source_mask=occlusion_mask(camera,(sw,sh),pose,z,bed,config['arm']);mask=cv2.remap(source_mask,mx,my,cv2.INTER_NEAREST,borderMode=cv2.BORDER_CONSTANT,borderValue=255);mask=cv2.dilate(mask,self.kernel);allowed=cv2.bitwise_and(valid,cv2.compare(mask,0,cv2.CMP_EQ));score=cv2.bitwise_and(base_score,base_score,mask=allowed);priority=float(camera.get('priority',1.))
            if priority!=1.:score=cv2.multiply(score,priority)
            scores[index]=score;visible[index]=cv2.countNonZero(allowed)/total;warped[index]=cv2.remap(frame,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
            choose=cv2.compare(score,best,cv2.CMP_GT);cv2.copyTo(self.labels[index],choose,winner);best=cv2.max(best,score)
        # Keep a valid current source across near-equal weights, avoiding flicker.
        if self.previous is not None and self.previous.shape==winner.shape:
            for index,score in scores.items():
                keep=cv2.bitwise_and(cv2.compare(self.previous,index,cv2.CMP_EQ),cv2.bitwise_and(cv2.compare(score,0,cv2.CMP_GT),cv2.compare(cv2.multiply(score,1.15),best,cv2.CMP_GE)));cv2.copyTo(self.labels[index],keep,winner)
        for index,frame in warped.items():
            selected=cv2.compare(winner,index,cv2.CMP_EQ);cv2.copyTo(frame,selected,out);contributions[str(views[index][0]['index'])]=round(cv2.countNonZero(selected)/total*100,2)
        missing_mask=cv2.compare(winner,0,cv2.CMP_LT);missing=missing_mask.astype(bool)
        if config.get('provenance',False):
            palette=[(40,40,240),(240,160,20),(60,220,80),(220,40,180),(30,220,240),(220,160,90),(120,80,240),(240,240,60)]
            for index in warped:
                selected=winner==index;out[selected]=(out[selected].astype(np.float32)*.7+np.asarray(palette[index%8])*.3).astype(np.uint8)
        self.previous=winner.copy()
        return out,{'coverage':round(100-cv2.countNonZero(missing_mask)/total*100,2),'contributions':contributions,'visible':visible,'valid_views':len(warped),'missing_mask':missing,'winner':winner}
