import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const $ = (id) => document.getElementById(id);
const clamp = THREE.MathUtils.clamp;
const viewport = $('viewport');
const stage = $('stage');
const FINGERS = ['thumb', 'index', 'middle', 'ring', 'pinky'];
const FINGER_SHORT = ['TH', 'IN', 'MI', 'RI', 'PI'];
const LINKS = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],[13,17],[0,17],[17,18],[18,19],[19,20]];
const MODE_NAMES = { idle:'Hands relaxed', hover:'Ready to select', grab:'Grab & move', rotate:'Rotate & twist', zoom:'Change model size', explode:'Separate components', next_part:'Next component', reset:'Reset model' };
const fingerElements = [];
for (let index = 0; index < 2; index++) {
  const row = document.createElement('div'); row.className = 'finger-row';
  const name = document.createElement('span'); name.className = 'finger-hand'; name.textContent = `H${index + 1}`; row.append(name);
  const indicators = FINGERS.map((finger, i) => {
    const element = document.createElement('span'); element.className = 'finger-indicator'; element.textContent = FINGER_SHORT[i]; element.title = `${finger}: no hand`; row.append(element); return element;
  });
  fingerElements.push({ name, indicators }); $('fingerStatus').append(row);
}

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(40, 1, 0.05, 100);
camera.position.set(5.6, 3.2, 7.8);
let renderer;
try {
  renderer = new THREE.WebGLRenderer({ antialias:true, alpha:true, powerPreference:'high-performance' });
} catch (error) {
  $('stageError').hidden = false;
  $('stageError').textContent = `3D graphics could not start. Open this page in a browser with WebGL 2 and hardware acceleration enabled. ${error.message}`;
  throw error;
}
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.45;
viewport.append(renderer.domElement);
renderer.domElement.addEventListener('webglcontextlost', (event) => {
  event.preventDefault(); cancelHold(); $('stageError').hidden = false;
  $('stageError').textContent = 'The graphics connection was interrupted. Reload the page to restart the 3D view.';
});
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true; controls.dampingFactor = 0.08;
controls.minDistance = 2.5; controls.maxDistance = 22;
controls.target.set(0, 0.05, 0); controls.update(); controls.saveState();
scene.add(new THREE.HemisphereLight(0xd8f7ff, 0x354542, 2.5));
const keyLight = new THREE.DirectionalLight(0xffe3c9, 4.5); keyLight.position.set(-4, 6, 5); scene.add(keyLight);
const rimLight = new THREE.DirectionalLight(0x83cbe7, 3.2); rimLight.position.set(4, 2, -4); scene.add(rimLight);
const fillLight = new THREE.DirectionalLight(0xd6ecd0, 1.6); fillLight.position.set(3, -3, 4); scene.add(fillLight);
const grid = new THREE.GridHelper(18, 36, 0x536a70, 0x344a52); grid.position.y = -2.43;
grid.material.transparent = true; grid.material.opacity = 0.28; scene.add(grid);
const assembly = new THREE.Group(); scene.add(assembly);
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
const baseRotation = new THREE.Euler(0, -0.35, 0);
const partMaterialOriginals = new WeakMap();
let parts = [];
let selected = null;
let explodeAmount = 0;

function material(color, metalness = 0.6, roughness = 0.35) {
  return new THREE.MeshStandardMaterial({ color, metalness, roughness });
}
function mesh(geometry, mat, parent, position = [0,0,0]) {
  const object = new THREE.Mesh(geometry, mat); object.position.fromArray(position); parent.add(object); return object;
}
function cylinder(radiusTop, radiusBottom, height, mat, parent, position) {
  return mesh(new THREE.CylinderGeometry(radiusTop, radiusBottom, height, 48), mat, parent, position);
}
function ring(radius, tube, mat, parent, y) {
  const object = mesh(new THREE.TorusGeometry(radius, tube, 10, 64), mat, parent, [0,y,0]); object.rotation.x = Math.PI / 2; return object;
}
function component(name, position, explosion, detail) {
  const object = new THREE.Group(); object.name = name; object.position.fromArray(position); assembly.add(object);
  const part = { object, name, home:object.position.clone(), offset:new THREE.Vector3(), explosion:new THREE.Vector3(...explosion), detail };
  parts.push(part); return object;
}
function clearModel() {
  const geometries = new Set(); const materials = new Set(); const textures = new Set();
  assembly.traverse((object) => {
    if (object.geometry) geometries.add(object.geometry);
    for (const mat of object.material ? (Array.isArray(object.material) ? object.material : [object.material]) : []) {
      materials.add(mat); for (const value of Object.values(mat)) if (value?.isTexture) textures.add(value);
    }
  });
  geometries.forEach((g) => g.dispose()); textures.forEach((t) => t.dispose()); materials.forEach((m) => m.dispose());
  assembly.clear(); parts = []; selected = null;
}
function createDemo() {
  clearModel();
  const silver = material(0xc4d1cd, 0.55, 0.3);
  const graphite = material(0x354a51, 0.7, 0.35);
  const copper = material(0xd99560, 0.55, 0.28);
  const teal = material(0x517d7f, 0.45, 0.35);
  const dark = material(0x1c2e36, 0.5, 0.4);

  const bell = component('Nozzle bell', [0,0,0], [0,-1.2,0], 'The flared lower component of this concept assembly.');
  const profile = [[1.12,-2.08],[1.04,-1.97],[.89,-1.72],[.7,-1.35],[.51,-.92],[.39,-.59],[.39,-.42],[.45,-.39]].map(([x,y]) => new THREE.Vector2(x,y));
  const nozzleMat = graphite.clone(); nozzleMat.side = THREE.DoubleSide;
  mesh(new THREE.LatheGeometry(profile, 64), nozzleMat, bell);
  ring(1.12,.035,copper,bell,-2.08);
  for (let i = 0; i < 8; i++) {
    const t = i / 7; const y = -1.9 + t * 1.25; const radius = .995 - .6 * t;
    ring(radius,.012,silver,bell,y);
  }
  const chamber = component('Combustion chamber', [0,.11,0], [0,0,0], 'The central body; select and move it to inspect the assembly.');
  cylinder(.49,.43,1.06,teal,chamber,[0,0,0]);
  for (let i = 0; i < 32; i++) {
    const angle = i / 32 * Math.PI * 2;
    const rib = cylinder(.014,.014,.91,silver,chamber,[Math.cos(angle)*.48,0,Math.sin(angle)*.48]); rib.rotation.z = .015;
  }
  ring(.49,.045,copper,chamber,.45); ring(.435,.045,copper,chamber,-.48);
  const injector = component('Injector head', [0,.77,0], [0,.65,0], 'An illustrative upper head with a circular bolt pattern.');
  cylinder(.57,.57,.2,copper,injector,[0,0,0]); cylinder(.42,.49,.22,dark,injector,[0,.17,0]);
  for(let i=0;i<12;i++){ const a=i/12*Math.PI*2; cylinder(.035,.035,.055,silver,injector,[Math.cos(a)*.48,.12,Math.sin(a)*.48]); }
  const manifold = component('Feed manifold', [0,1.31,0], [0,1.4,0], 'Illustrative pipes linking the upper feed assembly.');
  cylinder(.24,.31,.65,silver,manifold,[0,0,0]); ring(.26,.045,copper,manifold,.21);
  const cross = cylinder(.13,.13,1.52,teal,manifold,[0,.16,0]); cross.rotation.z = Math.PI/2;
  const pumpLeft = component('Pump assembly A', [-.87,.95,0], [-1.15,.45,0], 'A separate concept component for selection and exploded-view demonstrations.');
  cylinder(.27,.27,.65,graphite,pumpLeft,[0,0,0]); cylinder(.33,.33,.19,copper,pumpLeft,[0,-.22,0]); cylinder(.19,.23,.27,silver,pumpLeft,[0,.44,0]);
  const pumpRight = component('Pump assembly B', [.87,.95,0], [1.15,.45,0], 'A second concept component; these shapes are not a validated engine design.');
  cylinder(.27,.27,.65,graphite,pumpRight,[0,0,0]); cylinder(.33,.33,.19,copper,pumpRight,[0,-.22,0]); cylinder(.19,.23,.27,silver,pumpRight,[0,.44,0]);
  const feeds = component('External feed lines', [0,0,0], [0,0,1.1], 'Curved external tubing, grouped as one selectable part.');
  for (const side of [-1,1]) {
    const curve = new THREE.CatmullRomCurve3([new THREE.Vector3(side*.87,.65,.12),new THREE.Vector3(side*.91,.3,.3),new THREE.Vector3(side*.81,-.3,.38),new THREE.Vector3(side*.38,-.5,.25)]);
    mesh(new THREE.TubeGeometry(curve,32,.053,12,false),copper,feeds);
  }
  const mount = component('Upper mount', [0,1.91,0], [0,2.0,0], 'An illustrative mounting plate at the top of the assembly.');
  cylinder(.48,.35,.16,silver,mount,[0,0,0]); cylinder(.19,.19,.31,graphite,mount,[0,-.18,0]); ring(.41,.038,copper,mount,.09);
  $('modelTitle').textContent = 'Rocket engine';
  $('modelDescription').textContent = 'A conceptual assembly. Explore how the pieces fit together.';
  document.querySelector('.concept-tag').textContent = 'CONCEPT MODEL / NOT TO SCALE';
  rebuildPartList(); resetModel();
}

function rebuildPartList() {
  $('partList').replaceChildren(); $('partCount').textContent = `${parts.length}`;
  parts.forEach((part, index) => {
    part.object.traverse((object) => { if (object.isMesh) object.userData.part = part; });
    const button = document.createElement('button'); button.className = 'part-button'; button.setAttribute('aria-pressed','false');
    const number = document.createElement('span'); number.className='part-number'; number.textContent=String(index+1).padStart(2,'0');
    const title = document.createElement('span'); title.className='part-name'; title.textContent=part.name;
    const arrow = document.createElement('span'); arrow.className='part-arrow'; arrow.textContent='↗'; arrow.setAttribute('aria-hidden','true');
    button.append(number,title,arrow); button.title=part.name;
    button.addEventListener('click',()=>{cancelHold();selectPart(part);});
    part.button=button; $('partList').append(button);
  });
}
function selectPart(part) {
  selected=part;
  for(const item of parts){
    item.button?.setAttribute('aria-pressed',String(item===part));
    item.object.traverse((object)=>{
      if(!object.isMesh) return;
      // Demo parts share materials; clone once so selection never lights other parts.
      if(!object.userData.selectionMaterials){
        object.material=Array.isArray(object.material)?object.material.map((m)=>m.clone()):object.material.clone();
        object.userData.selectionMaterials=true;
      }
      for(const mat of Array.isArray(object.material)?object.material:[object.material]){
        if(!partMaterialOriginals.has(mat)) partMaterialOriginals.set(mat,{emissive:mat.emissive?.clone(),color:mat.color?.clone()});
        const original=partMaterialOriginals.get(mat);
        if(mat.emissive) mat.emissive.copy(original.emissive).add(item===part?new THREE.Color(0x244119):new THREE.Color(0));
        else if(mat.color) mat.color.copy(original.color).lerp(new THREE.Color(0xb8e986),item===part ? .25 : 0);
      }
    });
  }
  $('selectedName').textContent=part?.name || 'No component selected';
  $('selectedHint').textContent=part?.detail || 'Point and pinch to pick a part';
}
function nextPart(){const i=parts.indexOf(selected);selectPart(parts[(i+1)%parts.length]||null);}
function positionParts(){for(const part of parts)part.object.position.copy(part.home).addScaledVector(part.explosion,explodeAmount).add(part.offset);}
function fitExplodedAssembly(){
  assembly.updateMatrixWorld(true);camera.updateMatrixWorld(true);
  const bounds=new THREE.Box3().setFromObject(assembly);
  const vertical=Math.tan(THREE.MathUtils.degToRad(camera.fov/2));
  const horizontal=vertical*camera.aspect;
  let pullback=0;
  for(const x of [bounds.min.x,bounds.max.x])for(const y of [bounds.min.y,bounds.max.y])for(const z of [bounds.min.z,bounds.max.z]){
    const point=new THREE.Vector3(x,y,z).applyMatrix4(camera.matrixWorldInverse);
    pullback=Math.max(pullback,Math.abs(point.x)/(horizontal*.86)+point.z,Math.abs(point.y)/(vertical*.8)+point.z);
  }
  if(pullback>0){
    const backward=camera.getWorldDirection(new THREE.Vector3()).negate();
    camera.position.addScaledVector(backward,pullback+.08);
    controls.maxDistance=Math.max(controls.maxDistance,camera.position.distanceTo(controls.target)+.1);
    controls.update();
  }
}
function setExplode(value){
  const previous=explodeAmount;explodeAmount=clamp(value,0,1);positionParts();
  if(explodeAmount>previous)fitExplodedAssembly();
  $('explodeRange').value=String(explodeAmount);$('explodeValue').value=`${Math.round(explodeAmount*100)}%`;
}
function resetModel(){
  cancelHold();assembly.position.set(0,0,0);assembly.rotation.copy(baseRotation);assembly.scale.setScalar(1);
  parts.forEach((part)=>part.offset.set(0,0,0));setExplode(0);selectPart(null);controls.reset();
}
function hitAt(cursor){
  if(!cursor)return null;
  scene.updateMatrixWorld(true);camera.updateMatrixWorld(true);
  pointer.set(cursor[0]*2-1,1-cursor[1]*2);raycaster.setFromCamera(pointer,camera);
  return raycaster.intersectObject(assembly,true).find((hit)=>hit.object.userData.part)||null;
}
let mouseDown=null;
renderer.domElement.addEventListener('pointerdown',(event)=>{mouseDown=[event.clientX,event.clientY];cancelHold();});
renderer.domElement.addEventListener('pointerup',(event)=>{
  if(!mouseDown||Math.hypot(event.clientX-mouseDown[0],event.clientY-mouseDown[1])>5)return;
  const rect=renderer.domElement.getBoundingClientRect();
  const hit=hitAt([(event.clientX-rect.left)/rect.width,(event.clientY-rect.top)/rect.height]);
  selectPart(hit?.object.userData.part||null);mouseDown=null;
});

let paused=false;
let hold=null;
let lastEventId=null;
let blockedEventId=null;
let packet=null;
let lastPacketAt=0;
let lastSeq=-1;
let staleCleared=true;
let socket=null;
let reconnectTimer=null;
let stopped=false;
function cancelHold(block=true){hold=null;if(block)blockedEventId=lastEventId;$('gestureCursor').dataset.active='false';}
function setConnection(state,label,message){
  $('connectionBadge').dataset.state=state;
  if($('connectionBadge').textContent!==label)$('connectionBadge').textContent=label;
  if(message&&$('statusMessage').textContent!==message)$('statusMessage').textContent=message;
}
function finitePair(value){return Array.isArray(value)&&value.length>=2&&value.slice(0,2).every(Number.isFinite);}
function validFrame(data){
  return data&&data.type==='frame'&&Number.isSafeInteger(data.seq)&&Array.isArray(data.hands)&&data.hands.length<=2&&
    data.hands.every((hand)=>Array.isArray(hand.landmarks)&&hand.landmarks.length===21&&hand.landmarks.every((p)=>Array.isArray(p)&&p.length>=3&&p.slice(0,3).every(Number.isFinite)))&&
    data.gesture&&Number.isSafeInteger(data.gesture.event_id)&&Object.hasOwn(MODE_NAMES,data.gesture.mode)&&
    (data.gesture.cursor===null||finitePair(data.gesture.cursor))&&
    (data.gesture.distance===null||Number.isFinite(data.gesture.distance))&&
    (data.gesture.roll===null||Number.isFinite(data.gesture.roll));
}
function startSocket(){
  if(stopped)return;
  const host=window.location.hostname||'127.0.0.1';
  const bracketed=host.includes(':')&&!host.startsWith('[')?`[${host}]`:host;
  socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${bracketed}:8766`);
  socket.addEventListener('open',()=>{
    lastSeq=-1;lastEventId=null;blockedEventId=null;lastPacketAt=0;staleCleared=true;packet=null;
    setConnection('connecting','STARTING','Tracker connected. Waiting for camera frames…');
  });
  socket.addEventListener('message',(event)=>{
    if(typeof event.data!=='string'||event.data.length>65536)return;
    let data;try{data=JSON.parse(event.data);}catch{return;}
    if(!data||typeof data!=='object')return;
    if(data.type==='status'){
      const message=typeof data.message==='string'?data.message.slice(0,350):'Tracker status received';
      if(data.level==='error'){cancelHold();clearTracking();packet=null;lastPacketAt=0;staleCleared=true;setConnection('error','TRACKER ERROR',message);}
      else if(data.code==='demo')setConnection('live','MOUSE DEMO',message);
      else setConnection('connecting','STARTING',message);
      return;
    }
    if(!validFrame(data)||data.seq<=lastSeq)return;
    lastSeq=data.seq;packet=data;lastPacketAt=performance.now();staleCleared=false;
    setConnection('live','LIVE',data.hands.length?'Keep fingertips visible. Pinch deliberately to begin.':'Show one or both hands to the camera.');
    updateTracking(data);processGesture(data);
  });
  socket.addEventListener('close',()=>{
    cancelHold();clearTracking();packet=null;lastPacketAt=0;
    setConnection('offline','OFFLINE','Tracker disconnected. Reconnecting automatically; mouse controls are available.');
    reconnectTimer=setTimeout(startSocket,2000);
  });
  socket.addEventListener('error',()=>setConnection('offline','OFFLINE','Cannot reach the local tracker. Start the Python app; this view will reconnect.'));
}
function updateTracking(data){
  $('captureFps').textContent=Number.isFinite(data.capture_fps)?data.capture_fps.toFixed(1):'—';
  $('trackingFps').textContent=Number.isFinite(data.tracking_fps)?data.tracking_fps.toFixed(1):'—';
  const info=data.camera||{};
  $('cameraInfo').textContent=Number.isFinite(info.width)&&Number.isFinite(info.height)?`${info.width} × ${info.height} · requested ${Number.isFinite(info.requested_fps)?info.requested_fps:'—'} fps · mode ${Number.isFinite(info.negotiated_fps)?info.negotiated_fps.toFixed(0):'—'} fps`:'Camera mode unavailable';
  $('handCount').textContent=`${data.hands.length} / 2`;
  for(let i=0;i<2;i++){
    const hand=data.hands[i]; const row=fingerElements[i];
    row.name.textContent=hand?String(hand.id||`H${i+1}`).slice(0,2).toUpperCase():`H${i+1}`;
    row.indicators.forEach((element,index)=>{
      const finger=FINGERS[index];const extended=hand?.fingers?.[finger]===true;const pinched=finger==='thumb'?Object.values(hand?.pinches||{}).some((v)=>v===true):hand?.pinches?.[finger]===true;
      element.dataset.open=String(extended);element.dataset.pinch=String(pinched);
      element.title=`${hand?hand.id||`Hand ${i+1}`:`Hand ${i+1}`} ${finger}: ${!hand?'not detected':pinched?'pinched':extended?'extended':'folded'}`;
      element.setAttribute('aria-label',element.title);
    });
  }
  const mode=paused?'Gestures paused':data.hands.length?MODE_NAMES[data.gesture.mode]:'Waiting for hands';
  $('gestureName').textContent=mode;$('presentGesture').textContent=mode;drawHands(data.hands);
}
function clearTracking(){
  $('captureFps').textContent='—';$('trackingFps').textContent='—';$('handCount').textContent='0 / 2';
  $('gestureName').textContent=paused?'Gestures paused':'Waiting for hands';$('gestureCursor').hidden=true;
  $('presentGesture').textContent='Tracking unavailable';
  fingerElements.forEach((row)=>row.indicators.forEach((element,i)=>{element.dataset.open='false';element.dataset.pinch='false';element.title=`${FINGERS[i]}: not detected`;element.setAttribute('aria-label',element.title);}));
  drawHands([]);
}
function drawHands(hands){
  const canvas=$('handCanvas');const ctx=canvas.getContext('2d');const w=canvas.width,h=canvas.height;
  ctx.clearRect(0,0,w,h);ctx.strokeStyle='#273a43';ctx.lineWidth=1;
  for(let x=20;x<w;x+=40){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();}
  for(let y=20;y<h;y+=40){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke();}
  if(!hands.length){ctx.fillStyle='#91a7b0';ctx.font='20px sans-serif';ctx.textAlign='center';ctx.fillText('Waiting for hands',w/2,h/2);return;}
  hands.forEach((hand,index)=>{
    const color=index===0?'#b8e986':'#eca978';ctx.strokeStyle=color;ctx.lineWidth=3;
    for(const[a,b]of LINKS){ctx.beginPath();ctx.moveTo(hand.landmarks[a][0]*w,hand.landmarks[a][1]*h);ctx.lineTo(hand.landmarks[b][0]*w,hand.landmarks[b][1]*h);ctx.stroke();}
    hand.landmarks.forEach((point,i)=>{ctx.beginPath();ctx.arc(point[0]*w,point[1]*h,[4,8,12,16,20].includes(i)?5.5:3,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();});
  });
}
function startGesture(gesture){
  const cursor=gesture.cursor;
  const common={id:gesture.event_id,mode:gesture.mode,cursor:cursor?.slice(),roll:gesture.roll||0};
  if(gesture.mode==='grab'&&cursor){
    const hit=hitAt(cursor);const part=hit?.object.userData.part||null;selectPart(part);
    const anchor=hit?.point||assembly.getWorldPosition(new THREE.Vector3());
    const plane=new THREE.Plane().setFromNormalAndCoplanarPoint(camera.getWorldDirection(new THREE.Vector3()),anchor);
    const point=new THREE.Vector3();raycaster.ray.intersectPlane(plane,point);
    hold={...common,part,plane,point,start:(part?part.offset:assembly.position).clone()};
  }else if(gesture.mode==='rotate'&&cursor){hold={...common,quaternion:assembly.quaternion.clone()};}
  else if(gesture.mode==='zoom'&&gesture.distance>.001){hold={...common,distance:gesture.distance,scale:assembly.scale.x};}
  else if(gesture.mode==='explode'&&gesture.distance!==null){hold={...common,distance:gesture.distance,amount:explodeAmount};}
  else if(gesture.mode==='next_part'){nextPart();}
  else if(gesture.mode==='reset'){resetModel();}
}
function processGesture(data){
  const gesture=data.gesture;const isNew=gesture.event_id!==lastEventId;
  if(isNew){hold=null;lastEventId=gesture.event_id;blockedEventId=null;}
  if(gesture.cursor&&!paused&&data.hands.length){
    $('gestureCursor').hidden=false;$('gestureCursor').style.left=`${clamp(gesture.cursor[0],0,1)*100}%`;$('gestureCursor').style.top=`${clamp(gesture.cursor[1],0,1)*100}%`;
  }else $('gestureCursor').hidden=true;
  if(paused||!data.hands.length||document.hidden||$('helpDialog').open){cancelHold();return;}
  if(gesture.mode==='idle'||gesture.mode==='hover'){hold=null;$('gestureCursor').dataset.active='false';return;}
  if(blockedEventId===gesture.event_id)return;
  if(isNew)startGesture(gesture);
  if(!hold||hold.id!==gesture.event_id||hold.mode!==gesture.mode)return;
  $('gestureCursor').dataset.active='true';
  if(hold.mode==='grab'&&gesture.cursor){
    pointer.set(gesture.cursor[0]*2-1,1-gesture.cursor[1]*2);raycaster.setFromCamera(pointer,camera);
    const point=new THREE.Vector3();if(!raycaster.ray.intersectPlane(hold.plane,point))return;
    let delta=point.sub(hold.point);
    if(hold.part){assembly.updateMatrixWorld(true);const inverse=new THREE.Matrix4().copy(assembly.matrixWorld).invert();delta=delta.applyMatrix4(inverse).sub(new THREE.Vector3().applyMatrix4(inverse));}
    delta.clampLength(0,5);const target=hold.start.clone().add(delta);const position=hold.part?hold.part.offset:assembly.position;
    position.add(target.sub(position).clampLength(0,.3));if(hold.part)positionParts();
  }else if(hold.mode==='rotate'&&gesture.cursor){
    const dx=clamp(gesture.cursor[0]-hold.cursor[0],-.7,.7);const dy=clamp(gesture.cursor[1]-hold.cursor[1],-.7,.7);
    const rollDelta=gesture.roll===null?0:Math.atan2(Math.sin(gesture.roll-hold.roll),Math.cos(gesture.roll-hold.roll));
    const rotation=new THREE.Quaternion().setFromEuler(new THREE.Euler(dy*3.5,dx*5,-rollDelta,'XYZ'));
    const target=rotation.multiply(hold.quaternion);assembly.quaternion.rotateTowards(target,.24);
  }else if(hold.mode==='zoom'&&gesture.distance!==null){
    const target=clamp(hold.scale*gesture.distance/hold.distance,.35,3);assembly.scale.setScalar(assembly.scale.x+clamp(target-assembly.scale.x,-.1,.1));
  }else if(hold.mode==='explode'&&gesture.distance!==null){
    const target=clamp(hold.amount+(gesture.distance-hold.distance)*3,0,1);setExplode(explodeAmount+clamp(target-explodeAmount,-.12,.12));
  }
}

function setPaused(value){paused=value;cancelHold();$('pauseButton').setAttribute('aria-pressed',String(value));$('pauseButton').firstChild.textContent=value?'Resume gestures ':'Pause gestures ';$('gestureName').textContent=value?'Gestures paused':'Release, then make a gesture';$('gestureCursor').hidden=value;}
$('pauseButton').addEventListener('click',()=>setPaused(!paused));
$('resetButton').addEventListener('click',resetModel);
$('explodeRange').addEventListener('input',(event)=>{cancelHold();setExplode(Number(event.target.value));});
$('demoButton').addEventListener('click',()=>{cancelHold();createDemo();$('importStatus').textContent='Demo assembly restored.';$('importStatus').dataset.error='false';});
$('helpButton').addEventListener('click',()=>{$('helpDialog').showModal();cancelHold();});
$('closeHelp').addEventListener('click',()=>$('helpDialog').close());
async function togglePresentation(){
  const presenting=!document.body.classList.contains('presenting');
  document.body.classList.toggle('presenting',presenting);$('presentHint').hidden=!presenting;$('projectorButton').setAttribute('aria-pressed',String(presenting));
  try{if(presenting&&!document.fullscreenElement)await document.documentElement.requestFullscreen();else if(!presenting&&document.fullscreenElement)await document.exitFullscreen();}catch{/* The presentation layout also works when browser fullscreen is unavailable. */}
  resize();
}
$('projectorButton').addEventListener('click',togglePresentation);$('exitPresent').addEventListener('click',togglePresentation);
document.addEventListener('fullscreenchange',()=>{if(!document.fullscreenElement){document.body.classList.remove('presenting');$('presentHint').hidden=true;$('projectorButton').setAttribute('aria-pressed','false');resize();}});
window.addEventListener('keydown',(event)=>{
  if(event.ctrlKey||event.metaKey||event.altKey||['INPUT','TEXTAREA','SELECT'].includes(event.target.tagName))return;
  if($('helpDialog').open)return;
  const key=event.key.toLowerCase();
  if(['arrowleft','arrowright','arrowup','arrowdown','+','=','-','n','e','r','p','f','?'].includes(key))event.preventDefault();
  if(key.startsWith('arrow')){
    cancelHold();const x=key==='arrowleft'?-.1:key==='arrowright'?.1:0;const y=key==='arrowup'?.1:key==='arrowdown'?-.1:0;
    if(event.shiftKey){const offset=selected?selected.offset:assembly.position;offset.x=clamp(offset.x+x,-5,5);offset.y=clamp(offset.y+y,-5,5);positionParts();}
    else{assembly.rotation.y+=x;assembly.rotation.x-=y;}
  }else if(key==='+'||key==='='||key==='-'){cancelHold();assembly.scale.setScalar(clamp(assembly.scale.x+(key==='-'?-.1:.1),.35,3));}
  else if(key==='n'){cancelHold();nextPart();}else if(key==='e'){cancelHold();setExplode(explodeAmount>.5?0:1);}
  else if(key==='r')resetModel();else if(key==='p')setPaused(!paused);else if(key==='f')togglePresentation();
  else if(key==='?'){$('helpDialog').showModal();cancelHold();}
  else if(key==='escape'&&document.body.classList.contains('presenting'))togglePresentation();
});

function inspectGltf(buffer,isBinary){
  let json;
  if(isBinary){
    if(buffer.byteLength<20)throw new Error('The GLB file is incomplete.');
    const view=new DataView(buffer);
    if(view.getUint32(0,true)!==0x46546c67||view.getUint32(4,true)!==2||view.getUint32(8,true)!==buffer.byteLength)throw new Error('Use a valid glTF 2.0 GLB file.');
    const length=view.getUint32(12,true);if(view.getUint32(16,true)!==0x4e4f534a||length>buffer.byteLength-20)throw new Error('The GLB JSON chunk is invalid.');
    json=JSON.parse(new TextDecoder().decode(buffer.slice(20,20+length)));
  }else json=JSON.parse(new TextDecoder().decode(buffer));
  if(String(json.asset?.version)!=='2.0')throw new Error('Use glTF version 2.0.');
  if((json.extensionsUsed||[]).some((name)=>['KHR_draco_mesh_compression','EXT_meshopt_compression','KHR_texture_basisu'].includes(name)))throw new Error('Export an uncompressed model with PNG or JPEG textures.');
  for(const resource of [...(json.buffers||[]),...(json.images||[])]){
    if(resource.uri&&!resource.uri.startsWith('data:'))throw new Error('This model references external files. Export one GLB with all resources embedded.');
  }
  if(json.skins?.length)throw new Error('Use a static assembly without skinned meshes.');
  return json;
}
$('modelFile').addEventListener('change',async(event)=>{
  const file=event.target.files?.[0];if(!file)return;
  $('importStatus').dataset.error='false';$('importStatus').textContent='Opening model…';cancelHold();
  try{
    if(file.size>50*1024*1024)throw new Error('Choose a model smaller than 50 MB.');
    if(!/\.(glb|gltf)$/i.test(file.name))throw new Error('Choose a .glb or .gltf file.');
    const buffer=await file.arrayBuffer();const isBinary=/\.glb$/i.test(file.name);inspectGltf(buffer,isBinary);
    const manager=new THREE.LoadingManager();manager.setURLModifier((url)=>{if(!url.startsWith('data:')&&!url.startsWith('blob:'))throw new Error('External model resources are disabled.');return url;});
    const loader=new GLTFLoader(manager);const result=await loader.parseAsync(isBinary?buffer:new TextDecoder().decode(buffer),'');
    const root=result.scene;root.updateMatrixWorld(true);const meshes=[];root.traverse((object)=>{if(object.isMesh)meshes.push(object);});
    if(!meshes.length||meshes.length>500)throw new Error('Use a static model with 1–500 mesh components.');
    const bounds=new THREE.Box3().setFromObject(root);const size=bounds.getSize(new THREE.Vector3());const longest=Math.max(size.x,size.y,size.z);
    if(!Number.isFinite(longest)||longest<1e-8)throw new Error('The model has invalid or empty geometry.');
    const center=bounds.getCenter(new THREE.Vector3());const normalization=new THREE.Matrix4().makeScale(3.8/longest,3.8/longest,3.8/longest).multiply(new THREE.Matrix4().makeTranslation(-center.x,-center.y,-center.z));
    const prepared=meshes.map((source,index)=>{
      const object=new THREE.Mesh(source.geometry,Array.isArray(source.material)?source.material.map((m)=>m.clone()):source.material.clone());
      object.applyMatrix4(normalization.clone().multiply(source.matrixWorld));
      object.name=(source.name||`Component ${index+1}`).slice(0,160);return object;
    });
    clearModel();assembly.position.set(0,0,0);assembly.rotation.set(0,0,0);assembly.scale.setScalar(1);assembly.updateMatrixWorld(true);
    prepared.forEach((object,index)=>{
      assembly.add(object);object.updateMatrixWorld(true);
      const worldCenter=new THREE.Box3().setFromObject(object).getCenter(new THREE.Vector3());
      const direction=worldCenter.clone();
      if(direction.length()<.2){const angle=index*Math.PI*(3-Math.sqrt(5));direction.set(Math.cos(angle),((index%3)-1)*.7,Math.sin(angle));}
      direction.normalize().multiplyScalar(1.2+(index%4)*.18);
      parts.push({object,name:object.name,home:object.position.clone(),offset:new THREE.Vector3(),explosion:direction,detail:'Imported component. Exploded offsets are illustrative.'});
    });
    $('modelTitle').textContent=file.name.replace(/\.(glb|gltf)$/i,'');$('modelDescription').textContent='Your model, ready to explore. Select a component to inspect it.';
    document.querySelector('.concept-tag').textContent='IMPORTED MODEL / ILLUSTRATIVE EXPLOSION';
    rebuildPartList();resetModel();$('importStatus').textContent=`Opened ${parts.length} components. Textures stay in this browser.`;
  }catch(error){$('importStatus').dataset.error='true';$('importStatus').textContent=`Could not open model: ${error.message}`;}
  finally{event.target.value='';}
});

function resize(){const width=viewport.clientWidth,height=viewport.clientHeight;if(!width||!height)return;renderer.setSize(width,height);camera.aspect=width/height;camera.updateProjectionMatrix();}
new ResizeObserver(resize).observe(viewport);
let fpsFrames=0,fpsStart=performance.now(),lastRender=performance.now();
function render(now){
  const delta=Math.min((now-lastRender)/1000,.05);lastRender=now;
  // Tracking input only updates on received frames; rendering continues independently.
  controls.update(delta);renderer.render(scene,camera);
  fpsFrames++;if(now-fpsStart>=1000){$('renderFps').textContent=`${Math.round(fpsFrames*1000/(now-fpsStart))} RENDER FPS`;fpsFrames=0;fpsStart=now;}
  if(lastPacketAt&&now-lastPacketAt>500&&!staleCleared){staleCleared=true;cancelHold();clearTracking();setConnection('offline','STALE','Tracking frames paused. Release the gesture, then try again when tracking returns.');}
  requestAnimationFrame(render);
}
window.addEventListener('pagehide',()=>{stopped=true;clearTimeout(reconnectTimer);socket?.close();});
document.addEventListener('visibilitychange',()=>{if(document.hidden)cancelHold();});
createDemo();drawHands([]);resize();startSocket();requestAnimationFrame(render);
