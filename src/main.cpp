// RF5 WolfLab C3 1.0.2. Initialize networking before opening any socket.
#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <Preferences.h>
#include <esp_system.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <cJSON.h>

struct Config {
  String ssid="WiFi Gratis", title="Acceso Wi-Fi", campaign="WolfLab demo", location="Presentacion", identifierMode="campaign";
  uint16_t durationMin=15;
  uint8_t channel=6;
} cfg;
struct Session {String token,alias;uint32_t created=0;bool submitted=false;};
struct Record {uint32_t seq=0,uptimeMs=0;String alias,name,identifier,mode,campaign,location,ssid;};
constexpr uint16_t RECORD_CAP=128;
constexpr uint8_t SESSION_CAP=32;
constexpr uint32_t FORM_TTL=900000;
Record records[RECORD_CAP]; Session sessions[SESSION_CAP];
Preferences prefs; WebServer web(80); DNSServer dns; QueueHandle_t associationsQueue;
String bootId,lineBuffer;
bool active=false,restartRadio=false,lineOverflow=false,bootHandled=false;
uint32_t startedAt=0,nextSeq=1,associations=0,portalSessions=0,submissions=0,overwritten=0,rateLimited=0,lastPost=0,bootAt=0;
uint16_t recordHead=0,recordCount=0;uint8_t sessionHead=0;

const char PORTAL[] PROGMEM=R"HTML(<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Acceso Wi-Fi</title><style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;background:#0d1424;color:#eef3fb;font:16px system-ui}main{width:100%;max-width:420px;padding:30px;border:1px solid #35465e;border-radius:22px;background:#172237}h1{font-size:26px}p{color:#b8c6dc;line-height:1.6}label{display:block;margin:20px 0 8px;font-size:14px}input,button{width:100%;padding:13px;border-radius:10px;font:inherit}input{background:#0e182b;color:#fff;border:1px solid #455773}button{margin-top:22px;background:#83e4ba;color:#102c20;border:0;font-weight:700}.note{font-size:12px}</style></head><body><main><div>📶</div><h1>{{TITLE}}</h1><p>Completá los siguientes campos para continuar.</p>
<form action="/submit" method="post" autocomplete="off"><input type="hidden" name="token" value="{{TOKEN}}"><label for="name">Nombre o alias (opcional)</label><input id="name" name="name" maxlength="64" placeholder="Tu nombre o alias" autocomplete="off"><label for="identifier">{{IDENTIFIER}}</label><input id="identifier" name="identifier" required maxlength="32" pattern="[A-Za-z0-9._-]{1,32}" placeholder="{{PLACEHOLDER}}" autocomplete="off"><p class="note">No ingreses contraseñas, códigos MFA ni información bancaria.</p><button type="submit">Continuar</button></form></main></body></html>)HTML";

String htmlEscape(const String &s){String o;for(size_t i=0;i<s.length();i++){switch(s[i]){case '&':o+="&amp;";break;case '<':o+="&lt;";break;case '>':o+="&gt;";break;case '"':o+="&quot;";break;case '\'':o+="&#39;";break;default:o+=s[i];}}return o;}
bool validText(const String &s,size_t lo,size_t hi){
  if(s.length()<lo||s.length()>hi)return false;
  for(size_t i=0;i<s.length();){
    uint8_t c=(uint8_t)s[i++];if(c<32||c==127)return false;if(c<128)continue;
    unsigned n;uint32_t cp,minCp;
    if(c>=0xc2&&c<=0xdf){n=1;cp=c&31;minCp=0x80;}
    else if(c>=0xe0&&c<=0xef){n=2;cp=c&15;minCp=0x800;}
    else if(c>=0xf0&&c<=0xf4){n=3;cp=c&7;minCp=0x10000;}else return false;
    if(i+n>s.length())return false;
    while(n--){uint8_t b=(uint8_t)s[i++];if((b&0xc0)!=0x80)return false;cp=(cp<<6)|(b&63);}
    if(cp<minCp||cp>0x10ffff||(cp>=0xd800&&cp<=0xdfff))return false;
  }return true;
}
bool validIdentifier(const String &s){if(!validText(s,1,32))return false;for(size_t i=0;i<s.length();i++){char c=s[i];if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='.'||c=='_'||c=='-'))return false;}return true;}
String token(){char b[33];snprintf(b,sizeof(b),"%08lx%08lx%08lx%08lx",(unsigned long)esp_random(),(unsigned long)esp_random(),(unsigned long)esp_random(),(unsigned long)esp_random());return b;}
void headers(){web.sendHeader("Cache-Control","no-store");web.sendHeader("X-Content-Type-Options","nosniff");web.sendHeader("X-Frame-Options","DENY");web.sendHeader("Referrer-Policy","no-referrer");web.sendHeader("Content-Security-Policy","default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'");}
void clearSessions(){for(auto &s:sessions)s=Session{};sessionHead=0;}
void stopRadio(){web.stop();dns.stop();WiFi.softAPdisconnect(true);active=false;clearSessions();}
bool startRadio(){
  if(active)stopRadio();
  if(!WiFi.mode(WIFI_AP))return false;
  if(!WiFi.softAPConfig(IPAddress(192,168,4,1),IPAddress(192,168,4,1),IPAddress(255,255,255,0)))return false;
  active=WiFi.softAP(cfg.ssid.c_str(),nullptr,cfg.channel,false,4);
  // WiFi.mode initializes esp_netif/lwIP. DNS/HTTP may open sockets only after it.
  if(active){dns.start(53,"*",IPAddress(192,168,4,1));web.begin();startedAt=millis();}return active;
}
Session *findSession(const String &t){if(t.length()!=32)return nullptr;for(auto &s:sessions)if(s.token==t&&(uint32_t)(millis()-s.created)<FORM_TTL)return &s;return nullptr;}
String cookie(){String c=web.header("Cookie");int p=c.indexOf("wolf_session=");if(p<0)return "";p+=13;int e=c.indexOf(';',p);return c.substring(p,e<0?c.length():e);}
void educate(const String &alias){
  headers();String s=F("<!doctype html><html lang='es'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Ejercicio de seguridad</title><style>body{background:#0d1424;color:#e9eef8;font:18px system-ui;line-height:1.7;padding:8vw;max-width:800px;margin:auto}h1{color:#83e4ba}strong{color:#ffc780}</style><h1>🐺 Era un ejercicio de seguridad</h1><p>Tu referencia: <strong>");
  s+=htmlEscape(alias);s+=F("</strong></p><p>El nombre de una red no demuestra quién la administra. Verificá el SSID y el portal con los canales oficiales antes de entregar información corporativa.</p><p>Una Wi-Fi abierta no permite leer automáticamente tus conexiones HTTPS. Este ejercicio muestra la confianza depositada en un portal desconocido.</p><p>Desconectá y olvidá esta red. No se solicitó ninguna contraseña y este dispositivo no ofrece Internet.</p><p>Si ingresaste un dato sensible por error, contactá al equipo de Seguridad.</p></html>");
  web.send(200,"text/html; charset=utf-8",s);
}
void redirect(){headers();web.sendHeader("Location","http://192.168.4.1/");web.send(302,"text/plain","Portal: http://192.168.4.1/");}
void root(){
  if(!active){headers();web.send(503,"text/plain","Campana pausada");return;}
  Session *s=findSession(cookie());if(!s){s=&sessions[sessionHead];sessionHead=(sessionHead+1)%SESSION_CAP;*s=Session{};s->token=token();s->created=millis();portalSessions++;}
  if(s->submitted){educate(s->alias);return;}
  headers();web.sendHeader("Set-Cookie","wolf_session="+s->token+"; HttpOnly; SameSite=Strict; Path=/; Max-Age=900");
  String page(FPSTR(PORTAL));page.replace("{{TITLE}}",htmlEscape(cfg.title));page.replace("{{TOKEN}}",s->token);
  page.replace("{{IDENTIFIER}}",cfg.identifierMode=="employee"?"IMB / ID de empleado":"Codigo de campana");
  page.replace("{{PLACEHOLDER}}",cfg.identifierMode=="employee"?"Tu identificador":"Codigo asignado al ejercicio");web.send(200,"text/html; charset=utf-8",page);
}
void submit(){
  headers();if(!active){web.send(503,"text/plain","Campana pausada");return;}
  if(web.header("Content-Length").toInt()>1024){web.send(413,"text/plain","Formulario demasiado grande");return;}
  Session *s=findSession(web.arg("token"));if(!s){web.send(400,"text/plain; charset=utf-8","Sesion vencida. Abri http://192.168.4.1/");return;}
  if(s->submitted){educate(s->alias);return;}
  if(lastPost&&(uint32_t)(millis()-lastPost)<1000){rateLimited++;web.send(429,"text/plain","Espera un segundo y reintenta");return;}
  String name=web.arg("name"),id=web.arg("identifier");name.trim();id.trim();
  if(!validText(name,0,64)||!validIdentifier(id)){web.send(400,"text/plain; charset=utf-8","Datos invalidos: nombre hasta 64 bytes UTF-8; identificador 1-32 letras, numeros, punto, guion o guion bajo.");return;}
  char alias[24];snprintf(alias,sizeof(alias),"Oveja %03lu",(unsigned long)nextSeq);
  Record &r=records[recordHead];r=Record{};r.seq=nextSeq++;r.uptimeMs=millis();r.alias=alias;r.name=name;r.identifier=id;r.mode=cfg.identifierMode;r.campaign=cfg.campaign;r.location=cfg.location;r.ssid=cfg.ssid;
  recordHead=(recordHead+1)%RECORD_CAP;if(recordCount<RECORD_CAP)recordCount++;else overwritten++;
  s->submitted=true;s->alias=alias;lastPost=millis();submissions++;educate(s->alias);
}
cJSON *configJson(){cJSON *o=cJSON_CreateObject();cJSON_AddStringToObject(o,"ssid",cfg.ssid.c_str());cJSON_AddStringToObject(o,"title",cfg.title.c_str());cJSON_AddStringToObject(o,"campaign",cfg.campaign.c_str());cJSON_AddStringToObject(o,"location",cfg.location.c_str());cJSON_AddStringToObject(o,"identifierMode",cfg.identifierMode.c_str());cJSON_AddNumberToObject(o,"durationMin",cfg.durationMin);cJSON_AddNumberToObject(o,"channel",cfg.channel);return o;}
cJSON *statusJson(){
  cJSON *o=cJSON_CreateObject();cJSON_AddStringToObject(o,"firmware","RF5-WolfLab-C3");cJSON_AddStringToObject(o,"version","1.0.2");cJSON_AddStringToObject(o,"chip",ESP.getChipModel());cJSON_AddNumberToObject(o,"flashBytes",ESP.getFlashChipSize());cJSON_AddStringToObject(o,"bootId",bootId.c_str());cJSON_AddBoolToObject(o,"active",active);cJSON_AddNumberToObject(o,"uptimeMs",millis());
  cJSON_AddNumberToObject(o,"remainingSec",active?max(0L,(long)cfg.durationMin*60L-(long)((uint32_t)(millis()-startedAt)/1000)):0);
  cJSON_AddNumberToObject(o,"connectedNow",active?WiFi.softAPgetStationNum():0);cJSON_AddNumberToObject(o,"associations",associations);cJSON_AddNumberToObject(o,"portalSessions",portalSessions);cJSON_AddNumberToObject(o,"submissions",submissions);cJSON_AddNumberToObject(o,"stored",recordCount);cJSON_AddNumberToObject(o,"overwritten",overwritten);cJSON_AddNumberToObject(o,"rateLimited",rateLimited);cJSON_AddNumberToObject(o,"freeHeap",ESP.getFreeHeap());return o;
}
cJSON *recordJson(const Record &r){cJSON *o=cJSON_CreateObject();cJSON_AddNumberToObject(o,"seq",r.seq);cJSON_AddNumberToObject(o,"uptimeMs",r.uptimeMs);cJSON_AddStringToObject(o,"alias",r.alias.c_str());cJSON_AddStringToObject(o,"name",r.name.c_str());cJSON_AddStringToObject(o,"identifier",r.identifier.c_str());cJSON_AddStringToObject(o,"mode",r.mode.c_str());cJSON_AddStringToObject(o,"campaign",r.campaign.c_str());cJSON_AddStringToObject(o,"location",r.location.c_str());cJSON_AddStringToObject(o,"ssid",r.ssid.c_str());return o;}
bool getText(cJSON *o,const char *key,String &dest,size_t lo,size_t hi){cJSON *v=cJSON_GetObjectItemCaseSensitive(o,key);if(!cJSON_IsString(v)||!v->valuestring)return false;String s(v->valuestring);if(!validText(s,lo,hi))return false;dest=s;return true;}
bool parseConfig(cJSON *o,Config &c){
  if(!cJSON_IsObject(o)||!getText(o,"ssid",c.ssid,1,32)||!getText(o,"title",c.title,1,64)||!getText(o,"campaign",c.campaign,1,64)||!getText(o,"location",c.location,1,64)||!getText(o,"identifierMode",c.identifierMode,1,16))return false;
  if(c.identifierMode!="campaign"&&c.identifierMode!="employee")return false;
  cJSON *d=cJSON_GetObjectItemCaseSensitive(o,"durationMin"),*ch=cJSON_GetObjectItemCaseSensitive(o,"channel");
  if(!cJSON_IsNumber(d)||d->valuedouble!=d->valueint||d->valueint<1||d->valueint>240||!cJSON_IsNumber(ch)||ch->valuedouble!=ch->valueint||ch->valueint<1||ch->valueint>11)return false;
  c.durationMin=d->valueint;c.channel=ch->valueint;return true;
}
bool saveConfig(){cJSON *o=configJson();char *data=cJSON_PrintUnformatted(o);bool ok=data&&prefs.putString("config",data)==strlen(data);if(data)cJSON_free(data);cJSON_Delete(o);return ok;}
void sendJson(cJSON *o){char *s=cJSON_PrintUnformatted(o);if(s){Serial.print("@RF5 ");Serial.println(s);cJSON_free(s);}cJSON_Delete(o);}
void snapshot(cJSON *head){
  // Avoid allocating a complete tree and serialized copy for all 128 records.
  cJSON_AddBoolToObject(head,"ok",true);char *s=cJSON_PrintUnformatted(head);
  if(!s){cJSON_Delete(head);return;}size_t n=strlen(s);if(n&&s[n-1]=='}')s[n-1]=0;
  Serial.print("@RF5 ");Serial.print(s);Serial.print(",\"records\":[");cJSON_free(s);cJSON_Delete(head);
  uint16_t first=(recordHead+RECORD_CAP-recordCount)%RECORD_CAP;
  for(uint16_t i=0;i<recordCount;i++){cJSON *r=recordJson(records[(first+i)%RECORD_CAP]);char *data=cJSON_PrintUnformatted(r);if(i)Serial.print(',');Serial.print(data?data:"null");if(data)cJSON_free(data);cJSON_Delete(r);}
  Serial.println("]}");
}
void command(const String &line){
  cJSON *req=cJSON_Parse(line.c_str());if(!req)return;
  cJSON *id=cJSON_GetObjectItemCaseSensitive(req,"id"),*cmd=cJSON_GetObjectItemCaseSensitive(req,"cmd");
  if(!cJSON_IsString(id)||strlen(id->valuestring)>64||!cJSON_IsString(cmd)){cJSON_Delete(req);return;}
  cJSON *reply=cJSON_CreateObject();cJSON_AddStringToObject(reply,"id",id->valuestring);String op(cmd->valuestring),error;bool ok=true;
  if(op=="hello"||op=="snapshot"){cJSON_AddItemToObject(reply,"config",configJson());cJSON_AddItemToObject(reply,"status",statusJson());if(op=="snapshot"){snapshot(reply);cJSON_Delete(req);return;}}
  else if(op=="configure"){Config candidate;if(!parseConfig(cJSON_GetObjectItemCaseSensitive(req,"config"),candidate)){ok=false;error="Configuracion invalida";}else{Config before=cfg;cfg=candidate;if(!saveConfig()){cfg=before;ok=false;error="No se pudo guardar en NVS";}else{stopRadio();restartRadio=true;}}}
  else if(op=="pause")stopRadio();else if(op=="start"){ok=startRadio();if(!ok)error="No se pudo iniciar AP";}
  else if(op=="clear"){for(auto &r:records)r=Record{};recordHead=recordCount=0;associations=portalSessions=submissions=overwritten=rateLimited=0;clearSessions();}
  else{ok=false;error="Comando desconocido";}
  cJSON_AddBoolToObject(reply,"ok",ok);if(!ok)cJSON_AddStringToObject(reply,"error",error.c_str());sendJson(reply);cJSON_Delete(req);
}
void readSerial(){unsigned budget=256;while(budget--&&Serial.available()){char c=Serial.read();if(c=='\n'){if(!lineOverflow&&lineBuffer.length())command(lineBuffer);lineBuffer="";lineOverflow=false;break;}if(c=='\r')continue;if(lineBuffer.length()>=2048){lineOverflow=true;continue;}if(!lineOverflow)lineBuffer+=c;}}
void setup(){
  pinMode(WOLFLAB_LED_PIN,OUTPUT);digitalWrite(WOLFLAB_LED_PIN,HIGH);pinMode(WOLFLAB_BOOT_PIN,INPUT_PULLUP);
  Serial.begin(115200);Serial.setTxTimeoutMs(20);lineBuffer.reserve(2048);bootId=token().substring(0,16);prefs.begin("rf5-wolflab",false);
  String saved=prefs.getString("config","");if(saved.length()){cJSON *o=cJSON_Parse(saved.c_str());Config c;if(parseConfig(o,c))cfg=c;cJSON_Delete(o);}
  associationsQueue=xQueueCreate(16,sizeof(uint8_t));
  WiFi.onEvent([](WiFiEvent_t e,WiFiEventInfo_t info){(void)info;if(e==ARDUINO_EVENT_WIFI_AP_STACONNECTED&&associationsQueue){uint8_t v=1;xQueueSend(associationsQueue,&v,0);}});
  const char *keys[]={"Cookie","Content-Length"};web.collectHeaders(keys,2);web.on("/",HTTP_GET,root);web.on("/submit",HTTP_POST,submit);
  web.on("/wall",HTTP_GET,[](){headers();web.send(200,"text/plain; charset=utf-8","El mural y los registros se consultan desde el panel USB del operador.");});web.onNotFound(redirect);startRadio();
}
void loop(){
  uint8_t event;while(associationsQueue&&xQueueReceive(associationsQueue,&event,0)==pdTRUE)associations++;
  readSerial();if(restartRadio){restartRadio=false;startRadio();}
  if(active){dns.processNextRequest();web.handleClient();if((uint32_t)(millis()-startedAt)>=(uint32_t)cfg.durationMin*60000UL)stopRadio();}
  bool pressed=digitalRead(WOLFLAB_BOOT_PIN)==LOW;if(pressed&&!bootAt){bootAt=millis();bootHandled=false;}if(pressed&&!bootHandled&&(uint32_t)(millis()-bootAt)>3000){stopRadio();bootHandled=true;}if(!pressed)bootAt=0;
  digitalWrite(WOLFLAB_LED_PIN,active&&millis()%2000<100?LOW:HIGH);delay(2);
}
