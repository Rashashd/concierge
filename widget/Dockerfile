FROM node:20-alpine
WORKDIR /app
RUN printf '{"name":"widget","version":"0.1.0","scripts":{"start":"node server.js"}}' > package.json
RUN printf 'require("http").createServer((_,r)=>{r.end(JSON.stringify({status:"ok"}))}).listen(3000);\n' > server.js
CMD ["node", "server.js"]
