const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('index.html','utf8');
const code=html.split('// BEGIN IMPORT PHOTO')[1].split('// END IMPORT PHOTO')[0];
const reference=html.slice(html.indexOf('async function ajouterRef(fi)'),html.indexOf('\nfunction dessinerCreation()'));
const message={textContent:'',setAttribute(){}};
let fetches=0,refreshes=0;
const context=vm.createContext({document:{querySelectorAll:()=>[message]},
  CH:{avatar:null},FICHE:null,CR_REFS:[],encodeURIComponent,
  fetch:async()=>{fetches++;return {ok:true,status:200,json:async()=>({nom:'portrait.jpg'})}},
  rafraichir:async()=>{refreshes++;assert.equal(context.CH.avatar,'portrait.jpg')},
  dessiner:()=>{},dessinerCreation:()=>{}});
vm.runInContext(code+'\n'+reference,context);
(async()=>{
  // Windows may provide an empty MIME type: a JPEG filename still imports.
  await context.envoyer({name:'portrait.jpg',type:''},'photo');
  assert.equal(context.FICHE,'portrait.jpg');assert.equal(refreshes,1);
  assert.match(message.textContent,/Avatar ajouté/);
  context.fetch=async()=>({ok:false,status:500,json:async()=>({erreur:'Disque plein'})});
  await context.envoyer({name:'portrait.jpg',type:'image/jpeg'},'photo');
  assert.match(message.textContent,/Disque plein/);assert.equal(message.className,'tl-error');
  context.fetch=async()=>({ok:false,status:502,json:async()=>{throw Error('HTML')}});
  await context.envoyer({name:'portrait.jpg'},'photo');assert.match(message.textContent,/HTTP 502/);
  context.fetch=async()=>{throw Error('Failed to fetch')};
  await context.envoyer({name:'portrait.jpg'},'photo');assert.match(message.textContent,/Failed to fetch/);
  const calls=fetches;
  await context.envoyer({name:'portrait.heic'},'photo');assert.match(message.textContent,/JPG, PNG ou WebP/);
  assert.equal(fetches,calls);
  context.fetch=async()=>({ok:true,status:200,json:async()=>({nom:'portrait.jpg'})});
  context.rafraichir=async()=>{throw Error('Actualisation interrompue')};
  await context.envoyer({name:'portrait.jpg'},'photo');assert.match(message.textContent,/Fichier enregistré/);
  await context.ajouterRef({name:'portrait.jpg'});assert.equal(context.CR_REFS.length,1);
  assert.match(message.textContent,/Référence ajoutée/);
  context.fetch=async()=>({ok:false,status:403,json:async()=>({erreur:'Accès refusé'})});
  await context.ajouterRef({name:'portrait.jpg'});assert.equal(context.CR_REFS.length,1);
  assert.match(message.textContent,/Accès refusé/);
  console.log('Import photo : JPEG sans MIME, sélection, références et erreurs visibles OK.');
})().catch(e=>{console.error(e);process.exitCode=1});
