package com.k3bora.ultrastalker.tv

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.tv.material3.MaterialTheme
import androidx.tv.material3.Text
import com.google.zxing.BarcodeFormat
import com.google.zxing.EncodeHintType
import com.google.zxing.common.BitMatrix
import com.google.zxing.qrcode.QRCodeWriter
import com.google.zxing.qrcode.decoder.ErrorCorrectionLevel
import com.k3bora.ultrastalker.core.Sources
import com.k3bora.ultrastalker.relay.PhoneLink
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext

fun qrMatrix(text: String): BitMatrix = QRCodeWriter().encode(text, BarcodeFormat.QR_CODE, 0, 0, mapOf(EncodeHintType.MARGIN to 1, EncodeHintType.ERROR_CORRECTION to ErrorCorrectionLevel.M))

@Composable
fun Qr(text: String, modifier: Modifier) {
    val m = remember(text) { qrMatrix(text) }
    Canvas(modifier) {
        drawRect(Color.White)
        val cell = size.width / m.width
        for (y in 0 until m.height) for (x in 0 until m.width) if (m.get(x, y)) drawRect(Color.Black, Offset(x * cell, y * cell), Size(cell + 0.6f, cell + 0.6f))
    }
}

@Composable
fun RestoreScreen(app: AppState, link: PhoneLink? = null, preset: Sources.Restored? = null) {
    val phone = remember { link ?: PhoneLink() }
    var info by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var found by remember { mutableStateOf(preset) }
    var problem by remember { mutableStateOf<String?>(null) }
    val context = LocalContext.current
    val replace = remember { FocusRequester() }
    val fileButton = remember { FocusRequester() }

    fun read(name: String, bytes: ByteArray) {
        try {
            val r = Sources.readAny(name, bytes)
            found = r
            problem = null
        } catch (e: Exception) {
            problem = e.message ?: "This file could not be read."
        }
    }

    val picker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        val bytes = runCatching { context.contentResolver.openInputStream(uri)?.use { it.readBytes() } }.getOrNull()
        if (bytes == null) problem = "This file could not be opened." else read(uri.lastPathSegment ?: "file", bytes)
    }

    DisposableEffect(Unit) {
        onDispose { if (link == null) phone.close() }
    }
    LaunchedEffect(Unit) {
        info = withContext(Dispatchers.IO) { runCatching { phone.open() }.getOrDefault(emptyMap()) }
        while (isActive) {
            delay(700)
            val got = phone.take() ?: continue
            read(got.first, got.second)
        }
    }

    Box(Modifier.fillMaxSize()) {
        Backdrop()
        val r = found
        if (r != null) {
            Column(Modifier.fillMaxSize().padding(horizontal = 64.dp, vertical = 44.dp)) {
                Text("Backup received", style = MaterialTheme.typography.labelSmall, color = Gold.gold)
                Spacer(Modifier.height(6.dp))
                Text("${r.sources.size} servers found", style = MaterialTheme.typography.displaySmall, color = Gold.text)
                Spacer(Modifier.height(8.dp))
                Text(
                    "Replace the servers on this TV, or add these to them." + if (r.receiverOnly > 0) "  (${r.receiverOnly} playlist files that live on the receiver itself are skipped.)" else "",
                    style = MaterialTheme.typography.bodyMedium, color = Gold.dim,
                )
                Spacer(Modifier.height(20.dp))
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    r.sources.take(6).forEachIndexed { i, s ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Chip(s.kindLabel)
                            Spacer(Modifier.width(12.dp))
                            Text(s.title(i), style = MaterialTheme.typography.titleSmall, color = Gold.text, maxLines = 1)
                            Spacer(Modifier.width(12.dp))
                            Text(if (s.mac.startsWith("02:")) s.host else s.host + "  ·  " + s.mac, style = MaterialTheme.typography.bodySmall, color = Gold.dim, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                    }
                    if (r.sources.size > 6) Text("and ${r.sources.size - 6} more", style = MaterialTheme.typography.bodySmall, color = Gold.dim)
                }
                Spacer(Modifier.height(28.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                    GoldButton("Replace my servers", modifier = Modifier.focusRequester(replace)) {
                        app.save(r.sources)
                        app.toast.value = "${r.sources.size} servers restored"
                        app.back()
                    }
                    if (app.sources.isNotEmpty()) GoldButton("Add to my servers", primary = false) {
                        app.save(app.sources.toList() + r.sources)
                        app.toast.value = "Servers added"
                        app.back()
                    }
                    GoldButton("Cancel", primary = false) { found = null }
                }
            }
            LaunchedEffect(r) {
                delay(30)
                runCatching { replace.requestFocus() }
            }
        } else {
            Row(Modifier.fillMaxSize().padding(horizontal = 64.dp, vertical = 44.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Restore a backup", style = MaterialTheme.typography.displaySmall, color = Gold.text)
                    Spacer(Modifier.height(10.dp))
                    Text("Bring your servers from the receiver's Ultra Stalker backup.", style = MaterialTheme.typography.bodyLarge, color = Gold.dim)
                    Spacer(Modifier.height(28.dp))
                    Step(1, "Scan the code with your phone's camera", "The phone must be on the same Wi-Fi as the TV.")
                    Step(2, "Choose the backup file", "The ZIP from the receiver or the website, or a portals.txt.")
                    Step(3, "It appears here", "Then choose to replace or add your servers.")
                    Spacer(Modifier.height(20.dp))
                    problem?.let {
                        Text(it, style = MaterialTheme.typography.bodyMedium, color = Gold.red)
                        Spacer(Modifier.height(12.dp))
                    }
                    GoldButton("Open a file on this TV", Ic.folder, Modifier.focusRequester(fileButton), primary = false) {
                        try {
                            picker.launch("*/*")
                        } catch (_: Exception) {
                            app.toast.value = "This TV has no file picker: use the phone instead"
                        }
                    }
                }
                Spacer(Modifier.width(40.dp))
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    val url = info["url"].orEmpty()
                    Box(Modifier.size(250.dp).clip(RoundedCornerShape(22.dp)).background(Color.White).padding(14.dp), contentAlignment = Alignment.Center) {
                        if (url.isNotEmpty()) Qr(url, Modifier.fillMaxSize())
                        else if (info.isEmpty()) Spinner()
                        else Text("Connect the TV to your network first", color = Color.Black, style = MaterialTheme.typography.bodyMedium)
                    }
                    Spacer(Modifier.height(16.dp))
                    if (url.isNotEmpty()) {
                        Text("Or open on the phone:", style = MaterialTheme.typography.bodySmall, color = Gold.dim)
                        Text(url.substringBefore("/?"), style = MaterialTheme.typography.titleSmall, color = Gold.text)
                        Spacer(Modifier.height(6.dp))
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("Code ", style = MaterialTheme.typography.bodySmall, color = Gold.dim)
                            Text(info["code"].orEmpty().chunked(3).joinToString(" "), color = Gold.gold, fontSize = 22.sp, style = MaterialTheme.typography.titleLarge)
                        }
                    }
                }
            }
            LaunchedEffect(Unit) { runCatching { fileButton.requestFocus() } }
        }
    }
}

@Composable
private fun Step(n: Int, title: String, text: String) {
    Row(Modifier.padding(bottom = 16.dp)) {
        Box(Modifier.size(30.dp).clip(CircleShape).background(Gold.gold.copy(alpha = 0.16f)), contentAlignment = Alignment.Center) {
            Text("$n", color = Gold.gold, style = MaterialTheme.typography.labelLarge)
        }
        Spacer(Modifier.width(14.dp))
        Column {
            Text(title, style = MaterialTheme.typography.titleSmall, color = Gold.text)
            Text(text, style = MaterialTheme.typography.bodySmall, color = Gold.dim)
        }
    }
}
