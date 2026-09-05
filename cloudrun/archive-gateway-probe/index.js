import express from 'express';
const app=express();
const port=Number(process.env.PORT||8080);
app.get('/health',(_req,res)=>res.json({ok:true,probe:'nova-archive-gateway-probe'}));
app.listen(port,'0.0.0.0',()=>console.log(`probe:${port}`));
