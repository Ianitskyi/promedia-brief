/* Listening statistics for BRIEF (owner, 2026-11-17).
   briefListen(edition, place) returns update(position, total, playing): it reports once per edition
   and page view that listening started, reached half and reached the end. Sent through
   window.briefTrack (analytics.js); nothing is sent if the visitor turned analytics off. */
window.briefListen=function(edition,place){
  const sent={};
  function send(name,percent){
    const key=name+percent; if(sent[key])return; sent[key]=1;
    if(typeof window.briefTrack==='function') window.briefTrack(name,{brief_edition:edition,brief_place:place,percent});
  }
  return function(pos,total,playing){
    if(playing) send('brief_play',0);
    if(!total||!sent.brief_play0) return;
    const f=pos/total;
    if(f>=0.5) send('brief_progress',50);
    if(f>=0.95) send('brief_complete',100);
  };
};
