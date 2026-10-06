// Copyright (c) 2026 He-Zixuan. LicenseRef-Classroom-Personal-NonCommercial-1.0; see LICENSE.
// Fractional box-filter resampling to mono 16 kHz; batch 250 ms of PCM.
class ClassroomPCM extends AudioWorkletProcessor {
  constructor(){super();this.ratio=sampleRate/16000;this.weight=0;this.sum=0;this.out=new Int16Array(4000);this.index=0;this.port.onmessage=()=>{this.send();this.port.postMessage({flushed:true});};}
  send(){if(this.index){const data=this.out.slice(0,this.index);this.port.postMessage(data,[data.buffer]);this.index=0;}}
  process(inputs){const channels=inputs[0];if(!channels?.[0])return true;for(let i=0;i<channels[0].length;i++){let sample=0;for(const ch of channels)sample+=ch[i]/channels.length;let remain=1;while(remain>1e-6){const amount=Math.min(remain,this.ratio-this.weight);this.sum+=sample*amount;this.weight+=amount;remain-=amount;if(this.weight>=this.ratio-1e-6){const v=Math.max(-1,Math.min(1,this.sum/this.ratio));this.out[this.index++]=Math.round(v*32767);this.sum=0;this.weight=0;if(this.index===4000)this.send();}}}return true;}
}
registerProcessor('classroom-pcm',ClassroomPCM);
