const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('index.html','utf8');
const code=html.split('// BEGIN VOIX LOT')[1].split('// END VOIX LOT')[0];
const nodes={};const node=id=>nodes[id]??=( {value:id==='voix-lot-profil'?'voice':'',textContent:'',innerHTML:'',disabled:false} );
const context=vm.createContext({TextDecoder,Map,VOIX_LOT:[],VOIX_LOT_CHARGE:false,VOIX_LOT_ENVOI:false,
  VOIX:{ok:true,lots:[]},E:{taches:[]},$:node,profilsCompatibles:()=>[{id:'voice'}],
  esc:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),f:(d,n)=>d+'/'+n});
vm.runInContext(code,context);
const file=(name,text)=>({name,size:Buffer.byteLength(text),arrayBuffer:async()=>Uint8Array.from(Buffer.from(text)).buffer});
(async()=>{
  await context.importerLotVoix([file('un.txt','\uFEFF[amusée] Bonjour.'),file('deux.md','<emphasis>Salut</emphasis>')]);
  assert.equal(context.VOIX_LOT.length,2);assert.equal(context.VOIX_LOT[0].texte,'[amusée] Bonjour.');
  const draft=JSON.stringify(context.VOIX_LOT);
  await context.importerLotVoix([file('vide.txt','')]);
  assert.match(node('voix-lot-erreur').textContent,/vide.txt/);assert.equal(JSON.stringify(context.VOIX_LOT),draft);
  await context.importerLotVoix([{name:'utf16.txt',size:2,arrayBuffer:async()=>new Uint8Array([255,254]).buffer}]);
  assert.match(node('voix-lot-erreur').textContent,/UTF-8/);
  let calls=0,finish;
  context.api=async(url,data)=>{calls++;assert.equal(url,'/api/voix/lot');assert.equal(data.fichiers.length,2);await new Promise(r=>finish=r);return {ajoutees:2};};
  context.rafraichir=async()=>{};
  const sending=context.lancerLotVoix();await context.lancerLotVoix();assert.equal(calls,1);finish();await sending;
  assert.equal(context.VOIX_LOT.length,0);assert.match(node('voix-lot-message').textContent,/2 fichier/);
  context.VOIX.lots=[{id:'old',etat:'finie',params:{lot:'old-lot',nom_fichier:'Avant.txt',ordre:1,taille_lot:1},resultat:{fichier:'generated.wav'}}];
  context.dessinerLotVoix();assert.match(node('voix-lot-suivi').innerHTML,/Avant.txt/);assert.match(node('voix-lot-suivi').innerHTML,/download="Avant.wav"/);
  console.log('Voix par lot : import UTF-8, tags, rejet atomique, double clic et historique OK.');
})().catch(e=>{console.error(e);process.exitCode=1;});
