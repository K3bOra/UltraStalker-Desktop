package com.k3bora.ultrastalker.tv

import android.app.Activity
import android.content.ContentValues
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.provider.OpenableColumns
import android.util.Base64
import android.webkit.JavascriptInterface
import android.webkit.WebView
import com.k3bora.ultrastalker.relay.PhoneLink
import org.json.JSONObject
import java.io.File

/* Files for the page (window.USTVFiles): backups in and out.
   In: a phone on the same Wi-Fi sends the file (PhoneLink), or the TV's own file
   manager when it has one. Out: the TV's Download folder, and the phone can get it. */
class Files(private val activity: Activity, private val web: WebView) {
    val link = PhoneLink()

    companion object {
        const val PICK = 4711
    }

    private fun json(m: Map<String, String>) = JSONObject(m as Map<*, *>).toString()

    @JavascriptInterface
    fun phoneOpen(): String = try {
        json(link.open())
    } catch (e: Exception) {
        JSONObject().put("error", e.message ?: "").toString()
    }

    @JavascriptInterface
    fun phoneClose() = link.close()

    @JavascriptInterface
    fun phoneTake(): String {
        val f = link.take() ?: return ""
        return JSONObject().put("name", f.first).put("b64", Base64.encodeToString(f.second, Base64.NO_WRAP)).toString()
    }

    @JavascriptInterface
    fun offerFile(name: String, b64: String): String {
        val bytes = Base64.decode(b64, Base64.DEFAULT)
        val clean = name.replace(Regex("[\\\\/:*?\"<>|\\u0000-\\u001f]"), " ").trim().ifEmpty { "UltraStalker-file" }
        link.offer(clean, bytes)
        val saved = try {
            save(clean, bytes)
        } catch (_: Exception) {
            ""
        }
        val phone = try {
            JSONObject(link.open() as Map<*, *>)
        } catch (_: Exception) {
            JSONObject()
        }
        return JSONObject().put("ok", true).put("saved", saved).put("phone", phone).toString()
    }

    /* Download/Ultra Stalker on the TV */
    private fun save(name: String, bytes: ByteArray): String {
        if (Build.VERSION.SDK_INT >= 29) {
            val values = ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, name)
                put(MediaStore.MediaColumns.MIME_TYPE, if (name.endsWith(".zip", true)) "application/zip" else "application/octet-stream")
                put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/Ultra Stalker")
            }
            val uri = activity.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: return ""
            activity.contentResolver.openOutputStream(uri)?.use { it.write(bytes) } ?: return ""
            return "Download/Ultra Stalker/$name"
        }
        val dir = File(activity.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS), "Ultra Stalker")
        dir.mkdirs()
        File(dir, name).writeBytes(bytes)
        return File(dir, name).absolutePath
    }

    private fun pickIntent(type: String) = Intent(Intent.ACTION_GET_CONTENT).apply {
        addCategory(Intent.CATEGORY_OPENABLE)
        setType("*/*")
        if (type.isNotBlank() && type != "*/*") putExtra(Intent.EXTRA_MIME_TYPES, type.split(",").map { it.trim() }.filter { it.contains("/") }.toTypedArray())
    }

    @JavascriptInterface
    fun canPick(): Boolean = try {
        pickIntent("*/*").resolveActivity(activity.packageManager) != null
    } catch (_: Exception) {
        false
    }

    @JavascriptInterface
    fun pick(accept: String) {
        activity.runOnUiThread {
            try {
                @Suppress("DEPRECATION")
                activity.startActivityForResult(pickIntent(accept), PICK)
            } catch (_: Exception) {
            }
        }
    }

    /* the TV's file manager answered */
    fun picked(uri: Uri?) {
        if (uri == null) return
        Thread {
            try {
                val cr = activity.contentResolver
                var name = "file"
                cr.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c -> if (c.moveToFirst()) name = c.getString(0) ?: name }
                val bytes = cr.openInputStream(uri)?.use { it.readBytes() } ?: return@Thread
                if (bytes.size > PhoneLink.MAX) return@Thread
                val j = JSONObject().put("name", name).put("b64", Base64.encodeToString(bytes, Base64.NO_WRAP)).toString()
                web.post { web.evaluateJavascript("window.usTvPicked&&usTvPicked(" + JSONObject.quote(j) + ")", null) }
            } catch (_: Exception) {
            }
        }.start()
    }
}
