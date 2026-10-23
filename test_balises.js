const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('index.html','utf8'),ctx=vm.createContext({E:{balises:{curious:'curieux',serious:'serieux'}}});
vm.runInContext(html.slice(html.indexOf('function sansBalises('),html.indexOf('function ton(')),ctx);
const blocs=t=>JSON.parse(JSON.stringify(ctx.segmentsTexte(t)));
assert.deepEqual(blocs('[curious] Bonjour. [laughs] Ah ! [serious] [sighs] Bon.'),[{ton:'curieux',texte:'Bonjour. [laughs] Ah !'},{ton:'serieux',texte:'[sighs] Bon.'}]);
assert.deepEqual(blocs('[sighs] [curious] Bonjour.'),[{ton:'curieux',texte:'[sighs] Bonjour.'}]);
assert.equal(ctx.sansBalises('[curious] Bonjour [laughs]'),'Bonjour');
console.log('Balises : vocal cues preserved without extra visual blocks.');

vm.runInContext(html.slice(html.indexOf('function profilsCompatibles('),html.indexOf('function dessinerVoix(')),ctx);
ctx.VOIX={moteur:'drama3-mlx',voix:[{id:'drama',moteur_origine:'drama3-mlx'},{id:'omni',moteur_origine:'omnivoice'},{id:'ancien'}]};
assert.deepEqual(JSON.parse(JSON.stringify(ctx.profilsCompatibles())).map(v=>v.id),['drama','ancien']);
