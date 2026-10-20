// Regression tests for actual LTX output; no GPU or model is needed.
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const html=fs.readFileSync('index.html','utf8');
const parser=html.split('// BEGIN PROGRESSION PARSER')[1].split('// END PROGRESSION PARSER')[0];
const context=vm.createContext({});vm.runInContext(parser,context);
const parse=(s)=>context.analyserProgression(s,'Préparation');
let p=parse('Denoising:  25%|██ | 2/8 [00:24<01:09, 11.62s/it]');
assert.equal(p.pourcent,25);assert.equal(p.fait,2);assert.equal(p.total,8);assert.equal(p.restant,'01:09');assert.match(p.label,/passe 1\/2/);
p=parse('Denoising: 100%|██| 8/8 [01:14<00:00, 9.32s/it]\nDenoising: 33%|█| 1/3 [00:38<01:17, 38.76s/it]');
assert.equal(p.pourcent,33);assert.match(p.label,/passe 2\/2/);
p=parse('Denoising: 100%|██| 3/3 [01:57<00:00, 39.19s/it]\n[Loading decoders (VAE only, --no-audio)] ...\n[Decoding video (--no-audio)] ...');
assert.equal(p.pourcent,null);assert.equal(p.label,'Décodage de la vidéo');
p=parse('Denoising: 100%|██| 3/3 [01:57<00:00, 39.19s/it]\n$ ffmpeg -v error -y -i clip.mp4 preview.jpg');
assert.equal(p.pourcent,null);assert.match(p.label,/enregistrement/);
p=parse('[Loading text encoder (Gemma)] ...');assert.equal(p.pourcent,null);assert.match(p.label,/encodeur/);
p=parse('');assert.equal(p.pourcent,null);assert.equal(p.label,'Préparation');
// MuseTalk : la barre suit les images réellement écrites, pas ses barres tqdm internes déjà à 100 %.
p=parse('$ python lancer_musetalk15.py\n100%|██| 30/30 [00:20<00:00]\n[MuseTalk] Détection du visage\n[MuseTalk] Images 40/120');
assert.equal(p.pourcent,33);assert.equal(p.fait,40);assert.equal(p.label,'Synchronisation des lèvres');
p=parse('$ mflux-generate-flux2 --model x\n 50%|█| 2/4 [00:20<00:21, 10.2s/it]');assert.equal(p.pourcent,50);assert.equal(p.label,'Génération FLUX');assert.equal(p.restant,'00:21');
p=parse('[MuseTalk] Images 120/120\n[MuseTalk] Encodage');assert.equal(p.pourcent,null);assert.match(p.label,/Encodage/);
assert.ok(html.includes('await chargerProgressions();'));assert.ok(html.includes('afficherProgressions();'));
console.log('Progression: parser, pass changes, decoding, command resets and polling OK.');

// Mapping must not pass array index 0 as the optional actions=false argument.
const node={innerHTML:''};
Object.assign(context,{E:{taches:[{id:'test',type:'projet_clip',params:{},etat:'en cours'}]},esc:s=>String(s),minsec:s=>String(s),$:()=>node,document:{querySelectorAll:()=>[]}});
vm.runInContext(html.split('let SUIVI_TACHES={}')[1].split('let MODELES_SIGNATURE')[0].replace(/^;/,'').replace(/^/,'let SUIVI_TACHES={};'),context);
context.afficherProgressions();assert.match(node.innerHTML,/Annuler<\/button>/);

// API returns newest tasks first: a queued bridge must never hide the running clip.
const waiting={id:'bridge',params:{projet:'p'},etat:'en attente',cree:2};
const running={id:'clip3',params:{projet:'p'},etat:'en cours',cree:1};
assert.equal(context.choisirTacheProjet([waiting,running],'p').id,'clip3');
assert.equal(context.choisirTacheProjet([waiting,{...waiting,id:'older',cree:0}],'p').id,'older');
assert.equal(context.choisirTacheProjet([running],'other'),undefined);
// The displayed timeline reserves returns INSIDE spoken blocks (no extra duration).
const mp={blocs:[{id:'a',duree:2.32},{id:'b',duree:2.12},{id:'c',duree:2.32}]};
const mc=context.imagesBlocs(mp);
assert.equal(Object.values(mc).reduce((a,b)=>a+b,0),162);
assert.equal(context.raccordIntegre(mp,{gauche:'a',duree:.5}).coupe,44);
assert.equal(context.raccordIntegre(mp,{gauche:'a',duree:.5}).frames,12);
