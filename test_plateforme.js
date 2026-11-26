const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('index.html','utf8'),code=html.split('// BEGIN PLATFORM UI')[1].split('// END PLATFORM UI')[0];
const node={},alerts=[];
const context=vm.createContext({E:{plateforme:{os:'Windows',arch:'amd64',ram_gib:32},capacites:{video:{compatible:false,raison:'Pas de moteur LTX intégré pour Windows'},synthese:{compatible:true}}},$:()=>node,alert:s=>alerts.push(s)});
vm.runInContext(code,context);
assert.equal(context.verifierRole('video'),false);
assert.match(alerts[0],/Windows/);
assert.equal(context.verifierRole('synthese'),true);
context.afficherPlateforme();assert.match(node.textContent,/Windows/);assert.match(node.textContent,/32 Go RAM/);assert.match(node.textContent,/indisponible/);
const p={id:'projet',nom:'Test',avatar:'avatar.jpg',moteur:'a2v',revision:1,transitions:[],
  blocs:[{id:'bloc',clip:'clip.mp4',audio:'voix.wav',duree:2,revision:1,rendu_revision:1}]};
const timelineNodes=new Map();
const de=(id)=>{if(!timelineNodes.has(id))timelineNodes.set(id,{});return timelineNodes.get(id);};
Object.assign(context,{
  $:de,document:{querySelector:()=>null},PROJET:p.id,PROJETS:[p],ELEMENT:'bloc',TL_DIRTY:false,TL_EMPREINTE:'',
  monterMoniteur:()=>{},choisirTacheProjet:()=>null,imagesBlocs:()=>({bloc:48}),ton:()=>({nom:'Neutre'}),
  esc:String,f:(d,n)=>d+'/'+n,tige:String,barreVocale:()=>''
});
Object.assign(context.E,{taches:[],fichiers:{clips:[{nom:'clip.mp4'}],audios:[{nom:'voix.wav'}]}});
context.E.capacites.lipsync={compatible:false,raison:'MuseTalk indisponible'};
vm.runInContext(html.slice(html.indexOf('function mediaExiste('),html.indexOf('async function requeteProjet(')),context);
context.dessinerProjets();
assert.match(de('timeline-projet').innerHTML,/disabled onclick="lancerProjet\('automatique'\)"/);
assert.doesNotMatch(de('timeline-projet').innerHTML,/disabled onclick="lancerProjet\('export'\)"/);
assert.match(de('timeline-projet').innerHTML,/value="musetalk"\s+disabled/);
context.E.fichiers.clips=[];
context.dessinerProjets();
assert.match(de('timeline-projet').innerHTML,/disabled onclick="lancerProjet\('export'\)"/);
assert.match(de('timeline-projet').innerHTML,/Photo de référence/);
p.moteur='musetalk';
context.dessinerProjets();
assert.match(de('timeline-projet').innerHTML,/MuseTalk indisponible/);
console.log('Interface : système détecté, voix disponibles et génération vidéo indisponible expliquée.');
