import time
import pytz
import pandas as pd
from datetime import datetime
from iqoptionapi.stable_api import IQ_Option
import ta

# ⚠️ TUS DATOS REALES
EMAIL = "alvarengac555@gmail.com"       # ← Tu correo IQ Option
PASSWORD = "431745890c"           # ← Tu contraseña IQ Option
TIPO_CUENTA = "PRACTICE"             # Cuenta de prueba sin riesgo
PAR = "EURUSD-OTC"
TIMEFRAME = 1

MONTO_BASE = 1.0
MULTIPLICADOR = 2.0
MAX_PASOS_MG = 2
ATR_MINIMO = 0.0008
LIMITE_PERDIDA = 12.0
ZONA_HORARIA = "America/Asuncion"

API = None
memoria = {
    "call": {"wins":0, "losses":0, "racha":0, "bloqueado":False, "efectividad":0.0, "tiempo_bloqueo":None},
    "put": {"wins":0, "losses":0, "racha":0, "bloqueado":False, "efectividad":0.0, "tiempo_bloqueo":None},
    "perdida_acumulada": 0.0
}

def conectar():
    global API
    try:
        API = IQ_Option(EMAIL, PASSWORD)
        ok, razon = API.connect()
        if ok:
            print("✅ Conectado correctamente a IQ Option")
            API.change_balance(TIPO_CUENTA)
            return True
        print("❌ Error de conexión:", razon)
        API = None
        return False
    except Exception as e:
        print("❌ Excepción:", str(e))
        API = None
        return False

def verificar_conexion():
    if API is None or not API.check_connect():
        print("🔄 Reconectando...")
        return conectar()
    return True

def obtener_datos():
    if not verificar_conexion(): return pd.DataFrame()
    try:
        velas = API.get_candles(PAR, 60, 150, time.time())
        df = pd.DataFrame(velas)
        if df.empty or len(df)<60: return pd.DataFrame()
        df.rename(columns={'max':'high','min':'low'}, inplace=True)
        df['from'] = pd.to_datetime(df['from'], unit='s')
        df.set_index('from', inplace=True)
        df['volume'] = df['volume'].replace(0,1)
        return df
    except: return pd.DataFrame()

def actualizar_memoria(accion, ganancia):
    m = memoria[accion]
    if ganancia>0:
        m["wins"] +=1
        m["racha"] = max(m["racha"]+1,1)
        m["bloqueado"] = False
    else:
        m["losses"] +=1
        m["racha"] = min(m["racha"]-1,-1)
        memoria["perdida_acumulada"] += abs(ganancia)
    total = m["wins"]+m["losses"]
    m["efectividad"] = round((m["wins"]/total)*100,2) if total else 0
    if m["racha"] <= -2 or (total>=5 and m["efectividad"]<40):
        if not m["bloqueado"]:
            m["bloqueado"] = True
            m["tiempo_bloqueo"] = datetime.now(pytz.timezone(ZONA_HORARIA))
            print(f"🧠 {accion.upper()} BLOQUEADA | Efectividad: {m['efectividad']}%")

def desbloquear():
    ahora = datetime.now(pytz.timezone(ZONA_HORARIA))
    for acc in ["call","put"]:
        m = memoria[acc]
        if m["bloqueado"] and m["tiempo_bloqueo"]:
            mins = (ahora - m["tiempo_bloqueo"]).total_seconds()/60
            if mins >=20 or m["racha"]>0:
                m["bloqueado"] = False
                m["racha"] =0
                print(f"✅ {acc.upper()} DESBLOQUEADA")

def analizar(df):
    if df.empty or len(df)<60: return "NONE",0
    bb = ta.volatility.BollingerBands(close=df["close"], window=20, window_dev=2)
    df["bb_inf"] = bb.bollinger_lband()
    df["bb_sup"] = bb.bollinger_hband()
    df["atr"] = ta.volatility.AverageTrueRange(high=df["high"], low=df["low"], close=df["close"], window=14).average_true_range()
    df["ema20"] = ta.trend.EMAIndicator(close=df["close"], window=20).ema_indicator()
    df["ema50"] = ta.trend.EMAIndicator(close=df["close"], window=50).ema_indicator()
    ult = df.iloc[-1]
    if ult["atr"] < ATR_MINIMO or memoria["perdida_acumulada"] >= LIMITE_PERDIDA:
        return "NONE", ult["atr"]
    if ult["close"] <= ult["bb_inf"] and ult["ema20"]>ult["ema50"] and ult["close"]>ult["open"] and not memoria["call"]["bloqueado"]:
        return "call", ult["atr"]
    if ult["close"] >= ult["bb_sup"] and ult["ema20"]<ult["ema50"] and ult["close"]<ult["open"] and not memoria["put"]["bloqueado"]:
        return "put", ult["atr"]
    return "NONE", ult["atr"]

print("🚀 BOT 24/7 INICIADO")
conectar()
neto_total = 0.0

while True:
    try:
        ahora = datetime.now(pytz.timezone(ZONA_HORARIA))
        if ahora.second == 59:
            desbloquear()
            df = obtener_datos()
            accion, atr = analizar(df)

            if accion != "NONE":
                for paso in range(MAX_PASOS_MG + 1):
                    monto = round(MONTO_BASE * (MULTIPLICADOR ** paso), 2)
                    print(f"\n📊 {accion.upper()} | Paso {paso} | Monto: ${monto}")
                    ok, id_op = API.buy(monto, PAR, accion, TIMEFRAME)
                    if ok:
                        res = API.check_win_v3(id_op)
                        neto_total += res
                        actualizar_memoria(accion, res)
                        estado = "🟢 GANADO" if res > 0 else "🔴 PERDIDO" if res < 0 else "⚪ EMPATE"
                        print(f"{estado} | Neto: ${neto_total:.2f} | Efectividad: {memoria[accion]['efectividad']}%")
                        if res > 0:
                            break
                    else:
                        print("⚠️ Error al ejecutar orden")
                        break
            else:
                if ahora.minute % 5 == 0:
                    print(f"💤 {ahora.strftime('%H:%M')} | ATR: {atr:.5f} | Neto: ${neto_total:.2f}")
        time.sleep(0.3)
    except Exception as e:
        print(f"🔄 Error: {str(e)} | Reiniciando en 5s...")
        time.sleep(5)
