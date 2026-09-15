"use strict";
(() => {
  const data = JSON.parse(document.getElementById("candidate-data").textContent);
  const byId = new Map(data.cases.map(c => [c.case_id, c]));
  const drafts = new Map();
  const $ = id => document.getElementById(id);
  const label = text => text.replaceAll("_", " ");
  const titles = {pair:"Normal / defect pair", near:"Similar images", box:"Box correction", class:"Source class", source:"Source evidence"};
  let active = null, dirty = false, filtered = [], renderVersion = 0;
  const tell = text => { $("message").textContent = text; };
  const element = (tag, text) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; return node; };
  const svgNode = (tag, attrs) => { const node = document.createElementNS("http://www.w3.org/2000/svg",tag); for(const [key,value] of Object.entries(attrs)) node.setAttribute(key,String(value)); return node; };
  function progress() { $("reviewer").disabled = drafts.size > 0; $("progress").textContent = `${drafts.size} saved / ${data.cases.length} cases · ${filtered.length} shown`; }
  function draw() {
    $("images").replaceChildren();
    if (!active) return;
    const current = byId.get(active);
    const version = ++renderVersion; let pending = current.image_ids.length, failed = false;
    $("save").disabled = pending > 0;
    for (const id of current.image_ids) {
      const item = data.images[id], panel = element("div"); panel.className = "panel";
      const caption = element("p",`${item.condition} · ${item.source_split} · ${item.file}`); caption.className = "caption"; panel.append(caption);
      const scroll = element("div"); scroll.className = "canvas-scroll";
      const svg = svgNode("svg", {viewBox:`0 0 ${item.width} ${item.height}`,role:"img","aria-label":item.file});
      svg.style.width = `${Number($("zoom").value)*100}%`;
      svg.style.maxWidth = $("zoom").value === "1" ? "600px" : "none";
      svg.style.margin = "auto";
      const image = svgNode("image",{href:item.asset,width:item.width,height:item.height});
      image.addEventListener("load",()=>{if(version===renderVersion){pending--; $("save").disabled=failed || pending>0;}});
      image.addEventListener("error",()=>{if(version===renderVersion){failed=true; $("save").disabled=true; tell(`Image unavailable: ${item.file}. Visual decisions are disabled until its evidence loads.`);}}); svg.append(image);
      if ($("overlays").checked) {
        for (const annotation of item.annotations) {
          const [x,y,width,height] = annotation.bbox;
          svg.append(svgNode("rect",{x,y,width,height,fill:"none",stroke:"#ff4d61","stroke-width":1,"vector-effect":"non-scaling-stroke"}));
        }
        if(current.kind === "box") {
          const [x,y,width,height] = current.subject.after_xywh;
          svg.append(svgNode("rect",{x,y,width,height,fill:"none",stroke:"#ffe35b","stroke-width":2,"stroke-dasharray":"3 2","vector-effect":"non-scaling-stroke"}));
        }
      }
      scroll.append(svg); panel.append(scroll); $("images").append(panel);
    }
  }
  function show(id) {
    active = id; dirty = false; $("fields").replaceChildren(); tell("");
    $("save").disabled = !id; $("clear").disabled = !id;
    if (!id) { $("case-title").textContent="No matching cases"; $("hint").textContent="Adjust filters to continue."; $("subject").textContent=""; $("rationale").value=""; draw(); return; }
    const current = byId.get(id), saved = drafts.get(id);
    $("cases").value = id; $("case-title").textContent = titles[current.kind];
    $("hint").textContent = current.kind === "class" ? "Up to six source examples, not an exhaustive class audit. Use authoritative class definitions." : current.kind === "source" ? "Source provenance and physical-board independence require external reference evidence; images alone cannot establish them." : "Inspect the original evidence. Choose needs reference whenever the available evidence is insufficient.";
    $("subject").textContent = JSON.stringify(current.subject,null,2);
    for(const [key, choices] of Object.entries(data.fields[current.kind])) {
      const wrap = element("div"); wrap.className="answer";
      const title = element("label",label(key)); title.htmlFor=`answer-${key}`;
      const select = element("select"); select.id=`answer-${key}`; select.dataset.answer=key;
      const blank=element("option","Choose an answer"); blank.value=""; select.append(blank);
      for(const value of choices) { const option=element("option",label(value)); option.value=value; select.append(option); }
      select.value=saved?.answers[key] || ""; select.addEventListener("change",()=>dirty=true);
      wrap.append(title,select); $("fields").append(wrap);
    }
    $("rationale").value=saved?.rationale || ""; draw(); progress();
  }
  function canLeave() { return !dirty || window.confirm("Discard the unsaved edits to this case?"); }
  function filter() {
    if(!canLeave()) return;
    const query=$("search").value.toLowerCase();
    filtered=data.cases.filter(c=>(!$("kind").value || c.kind===$("kind").value) && (!query || (c.search+" "+c.case_id+" "+JSON.stringify(c.subject)).toLowerCase().includes(query)) && (!$("status").value || ($("status").value==="saved")===drafts.has(c.case_id)));
    $("cases").replaceChildren();
    for(const c of filtered) { const option=element("option",`${drafts.has(c.case_id)?"Saved · ":""}${titles[c.kind]} · ${c.search || c.subject.source_name || c.subject.topic || c.case_id}`); option.value=c.case_id; $("cases").append(option); }
    show(filtered.some(c=>c.case_id===active)?active:filtered[0]?.case_id || null); progress();
  }
  $("source").textContent=`${data.source} · source images verified when package was built`;
  for(const id of ["kind","status","search"]) $(id).addEventListener(id==="search"?"input":"change",filter);
  $("cases").addEventListener("change",()=>{if(canLeave()) show($("cases").value); else $("cases").value=active;});
  for(const [id,step] of [["previous",-1],["next",1]]) $(id).addEventListener("click",()=>{if(!canLeave()) return;const index=filtered.findIndex(c=>c.case_id===active)+step;if(filtered[index]) show(filtered[index].case_id);});
  $("zoom").addEventListener("change",draw); $("overlays").addEventListener("change",draw);
  $("rationale").addEventListener("input",()=>dirty=true);
  $("save").addEventListener("click",()=>{
    if(!active) return;
    if(!$("reviewer").value.trim()) return tell("Enter the actual reviewer identifier before saving.");
    const answers=Object.fromEntries([...$("fields").querySelectorAll("select")].map(s=>[s.dataset.answer,s.value]));
    const rationale=$("rationale").value.trim();
    if(Object.values(answers).some(v=>!v) || !rationale) return tell("Complete every answer and provide reference evidence before saving.");
    drafts.set(active,{case_id:active,answers,rationale}); dirty=false; filter(); tell("Decision saved in this page. Export to keep it.");
  });
  $("clear").addEventListener("click",()=>{if(active && canLeave()){drafts.delete(active);dirty=false;filter();tell("Saved decision cleared from this page.");}});
  $("export").addEventListener("click",()=>{
    const reviewer=$("reviewer").value.trim();
    if(dirty) return tell("Save or discard the current edits before exporting.");
    if(!reviewer || !drafts.size) return tell("Enter the actual reviewer identifier and save at least one decision.");
    const batch={schema_version:"1.0",packet_sha256:data.packet_sha256,reviewer,reviewed_at:new Date().toISOString(),decisions:[...drafts.values()]};
    const url=URL.createObjectURL(new Blob([JSON.stringify(batch,null,2)+"\n"],{type:"application/json"}));
    const link=element("a");link.href=url;link.download="candidate-decisions.json";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);tell("Saved decisions exported. Import them with the versioned decision command to record a ledger.");
  });
  $("import").addEventListener("change",async event=>{
    const file=event.target.files[0];if(!file) return;
    try {
      if(dirty) throw Error("Save or discard current edits before restoring decisions.");
      if(file.size>5000000) throw Error("Decision file exceeds 5 MB.");
      const batch=JSON.parse(await file.text());
      const exact=(obj,keys)=>obj && typeof obj==="object" && !Array.isArray(obj) && Object.keys(obj).sort().join("|")===keys.sort().join("|");
      if(!exact(batch,["schema_version","packet_sha256","reviewer","reviewed_at","decisions"]) || batch.schema_version!=="1.0" || batch.packet_sha256!==data.packet_sha256) throw Error("Decision file belongs to a different packet or schema.");
      if(typeof batch.reviewer!=="string" || !batch.reviewer.trim() || batch.reviewer.length>200 || typeof batch.reviewed_at!=="string" || !/(Z|[+-]\d{2}:\d{2})$/.test(batch.reviewed_at) || !Number.isFinite(Date.parse(batch.reviewed_at))) throw Error("Reviewer or timestamp is invalid.");
      if(drafts.size && $("reviewer").value.trim()!==batch.reviewer) throw Error("Keep different reviewers in separate exports.");
      if(!Array.isArray(batch.decisions) || !batch.decisions.length || batch.decisions.length>data.cases.length) throw Error("Invalid decision list.");
      const incoming=new Map();
      for(const d of batch.decisions) {
        if(!exact(d,["case_id","answers","rationale"]) || !byId.has(d.case_id) || incoming.has(d.case_id)) throw Error("Unknown or repeated case.");
        const fields=data.fields[byId.get(d.case_id).kind];
        if(!exact(d.answers,Object.keys(fields)) || Object.entries(fields).some(([key,choices])=>!choices.includes(d.answers[key])) || typeof d.rationale!=="string" || !d.rationale.trim() || d.rationale.length>4000) throw Error("Invalid answer or rationale.");
        if(drafts.has(d.case_id) && (JSON.stringify(drafts.get(d.case_id).answers)!==JSON.stringify(d.answers) || drafts.get(d.case_id).rationale!==d.rationale)) throw Error("Conflicting saved decision. Keep exports separate or clear that case first.");
        incoming.set(d.case_id,d);
      }
      for(const [key,value] of incoming) drafts.set(key,value);
      $("reviewer").value=batch.reviewer;filter();tell(`Restored ${incoming.size} decisions. Originals remain in your exported file.`);
    } catch(error) {tell(error.message);} finally {event.target.value="";}
  });
  window.addEventListener("beforeunload",event=>{if(dirty || drafts.size){event.preventDefault();event.returnValue="";}});
  filter();
})();
