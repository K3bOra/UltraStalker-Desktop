package com.k3bora.ultrastalker.relay

import com.google.zxing.BarcodeFormat
import com.google.zxing.EncodeHintType
import com.google.zxing.qrcode.QRCodeWriter
import com.google.zxing.qrcode.decoder.ErrorCorrectionLevel
import fi.iki.elonen.NanoHTTPD
import java.net.Inet4Address
import java.net.NetworkInterface
import java.security.SecureRandom
import java.util.concurrent.ConcurrentHashMap

/* Files between the TV and a phone on the same Wi-Fi.

   A TV usually has no file picker and no way to save a download where people can find
   it. So, while the TV shows its "file" window, this small server listens on the home
   network: the phone opens its address (QR code), enters nothing more than the code
   that is already in the link, sends a backup to the TV or gets one from it.
   It only answers with the right code, and stops by itself after 20 minutes. */
class PhoneLink(private val port: Int = 47391) {
    private val random = SecureRandom()
    @Volatile var code: String = newCode()
        private set
    private var server: Server? = null
    @Volatile private var until = 0L
    private class Item(val name: String, val bytes: ByteArray)
    @Volatile private var inbox: Item? = null
    private val outbox = ConcurrentHashMap<String, Item>()
    private val order = ArrayList<String>()

    companion object {
        const val MAX = 40 * 1024 * 1024

        fun lanAddress(): String? = try {
            NetworkInterface.getNetworkInterfaces().toList()
                .filter { it.isUp && !it.isLoopback && !it.isVirtual }
                .sortedBy { if (it.name.startsWith("eth")) 0 else if (it.name.startsWith("wlan")) 1 else 2 }
                .flatMap { it.inetAddresses.toList() }
                .firstOrNull { it is Inet4Address && it.isSiteLocalAddress }?.hostAddress
        } catch (_: Exception) {
            null
        }

        /* a QR code as an SVG picture (no Android graphics needed) */
        fun qrSvg(text: String): String {
            val m = QRCodeWriter().encode(text, BarcodeFormat.QR_CODE, 0, 0, mapOf(EncodeHintType.MARGIN to 2, EncodeHintType.ERROR_CORRECTION to ErrorCorrectionLevel.M))
            val sb = StringBuilder("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 ${m.width} ${m.height}' shape-rendering='crispEdges'><rect width='100%' height='100%' fill='#fff'/><path fill='#000' d='")
            for (y in 0 until m.height) for (x in 0 until m.width) if (m.get(x, y)) sb.append("M$x ${y}h1v1h-1z")
            return sb.append("'/></svg>").toString()
        }

        fun esc(s: String) = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;")
    }

    private fun newCode() = (100000 + random.nextInt(900000)).toString()

    /* start (or keep) listening; the address and the QR code for the TV's window */
    @Synchronized
    fun open(): Map<String, String> {
        until = System.currentTimeMillis() + 20 * 60_000
        if (server == null) {
            code = newCode()
            server = Server().also { it.start(15000, true) }
        }
        val ip = lanAddress() ?: ""
        val url = if (ip.isEmpty()) "" else "http://$ip:${server!!.listeningPort}/?c=$code"
        return mapOf("ip" to ip, "port" to server!!.listeningPort.toString(), "code" to code, "url" to url, "qr" to if (url.isEmpty()) "" else qrSvg(url))
    }

    @Synchronized
    fun close() {
        server?.stop()
        server = null
        inbox = null
    }

    /* the file the phone sent, once */
    fun take(): Pair<String, ByteArray>? {
        val i = inbox ?: return null
        inbox = null
        return i.name to i.bytes
    }

    /* a file for the phone to get */
    fun offer(name: String, bytes: ByteArray): String {
        val id = Relay.newId().take(10)
        synchronized(order) {
            outbox[id] = Item(name, bytes)
            order += id
            while (order.size > 5) outbox.remove(order.removeAt(0))
        }
        return id
    }

    private inner class Server : NanoHTTPD("0.0.0.0", port) {
        override fun serve(s: IHTTPSession): Response {
            val r = answer(s)
            // a refused upload leaves its body unread: never reuse that connection
            if (s.method == Method.POST && r.status != Response.Status.OK) r.addHeader("Connection", "close")
            return r
        }

        private fun answer(s: IHTTPSession): Response {
            if (System.currentTimeMillis() > until) {
                Thread { close() }.start()
                return text(Response.Status.FORBIDDEN, "Open the file window on the TV again.")
            }
            val c = s.parameters["c"]?.firstOrNull() ?: ""
            val path = s.uri ?: "/"
            if (path == "/" || path == "/index.html") return page(c == code)
            if (c != code) return text(Response.Status.FORBIDDEN, "Wrong code")
            if (path == "/up" && s.method == Method.POST) {
                val len = s.headers["content-length"]?.toIntOrNull() ?: return text(Response.Status.BAD_REQUEST, "No file")
                if (len <= 0 || len > MAX) return text(Response.Status.BAD_REQUEST, "The file is too big")
                val buf = ByteArray(len)
                var read = 0
                while (read < len) {
                    val n = s.inputStream.read(buf, read, len - read)
                    if (n < 0) break
                    read += n
                }
                if (read != len) return text(Response.Status.BAD_REQUEST, "The file didn't arrive whole")
                val name = (s.parameters["n"]?.firstOrNull() ?: "file").replace(Regex("[\\\\/:*?\"<>|\\u0000-\\u001f]"), " ").take(120)
                inbox = Item(name, buf)
                return text(Response.Status.OK, "ok")
            }
            val f = Regex("^/f/([A-Za-z0-9]+)$").find(path)
            if (f != null) {
                val item = outbox[f.groupValues[1]] ?: return text(Response.Status.NOT_FOUND, "Gone")
                val r = newFixedLengthResponse(Response.Status.OK, "application/octet-stream", item.bytes.inputStream(), item.bytes.size.toLong())
                r.addHeader("Content-Disposition", "attachment; filename=\"" + item.name.replace("\"", "") + "\"")
                return r
            }
            return text(Response.Status.NOT_FOUND, "Not found")
        }

        private fun text(st: Response.Status, t: String) = newFixedLengthResponse(st, "text/plain; charset=utf-8", t)

        private fun page(ok: Boolean): Response {
            val files = synchronized(order) { order.mapNotNull { id -> outbox[id]?.let { id to it.name } } }.reversed()
            val list = if (files.isEmpty()) "" else "<h2>From the TV · من التلفزيون</h2>" + files.joinToString("") { (id, n) -> "<a class='file' href='/f/$id?c=$code' download='${esc(n)}'>⬇ ${esc(n)}</a>" }
            val body = if (!ok) """
                <h1>Ultra Stalker TV</h1><p>Scan the code on the TV again.<br><span class=ar>امسح الكود اللي على التلفزيون تاني.</span></p>""" else """
                <h1>Ultra Stalker TV</h1>
                <h2>Send to the TV · ابعت للتلفزيون</h2>
                <label class=pick><input id=f type=file><span id=fn>Choose the file · اختار الملف</span></label>
                <button id=go disabled>Send · ابعت</button><p id=st></p>
                $list
                <script>
                const f=document.getElementById('f'),go=document.getElementById('go'),st=document.getElementById('st');
                f.onchange=()=>{document.getElementById('fn').textContent=f.files[0]?f.files[0].name:'Choose the file';go.disabled=!f.files[0]};
                go.onclick=async()=>{const x=f.files[0];if(!x)return;go.disabled=true;st.textContent='Sending… جاري الإرسال';
                  try{const r=await fetch('/up?c=$code&n='+encodeURIComponent(x.name),{method:'POST',body:x});st.textContent=r.ok?'✓ Sent — look at the TV · اتبعت، بص على التلفزيون':'✗ '+await r.text()}catch(e){st.textContent='✗ '+e.message}go.disabled=false};
                </script>"""
            val html = """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Ultra Stalker TV</title>
                <style>body{margin:0;padding:28px 20px;background:#0b0906;color:#f3e7c7;font:16px/1.5 system-ui,sans-serif}h1{color:#e9cd8b;font-size:22px;margin:0 0 18px}
                h2{font-size:15px;color:#d8c08a;margin:26px 0 10px}.pick{display:block;padding:18px;border:1px dashed rgba(240,222,180,.5);border-radius:16px;text-align:center}
                .pick input{display:none}button{margin-top:14px;width:100%;padding:15px;border:0;border-radius:999px;background:linear-gradient(135deg,#f3dfa6,#c9a25a);color:#1a1306;font-weight:800;font-size:16px}
                button:disabled{opacity:.45}.file{display:block;margin:8px 0;padding:14px 16px;border-radius:14px;background:rgba(255,240,210,.07);color:#f6e7b8;text-decoration:none;word-break:break-all}.ar{direction:rtl}</style></head><body>$body</body></html>"""
            return newFixedLengthResponse(Response.Status.OK, "text/html; charset=utf-8", html)
        }
    }
}
