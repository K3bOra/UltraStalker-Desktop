package com.k3bora.ultrastalker.tv

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.tv.material3.Icon
import androidx.tv.material3.MaterialTheme
import androidx.tv.material3.Text
import com.k3bora.ultrastalker.core.Media
import com.k3bora.ultrastalker.core.Source
import com.k3bora.ultrastalker.core.SourceKind
import com.k3bora.ultrastalker.core.Sources
import com.k3bora.ultrastalker.core.providerFor
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/* A text box for the remote: a tile you open with OK; the TV's keyboard comes up,
   and Done (or moving away) closes it. */
@Composable
fun InputField(
    label: String, value: String, onChange: (String) -> Unit, hint: String, modifier: Modifier = Modifier,
    type: KeyboardType = KeyboardType.Uri, secret: Boolean = false,
) {
    var editing by remember { mutableStateOf(false) }
    var back by remember { mutableStateOf(false) }
    val tile = remember { FocusRequester() }
    val field = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current
    Column(modifier) {
        Text(label, style = MaterialTheme.typography.labelMedium, color = Gold.dim, modifier = Modifier.padding(start = 4.dp, bottom = 6.dp))
        if (!editing) {
            Tile(onClick = { editing = true }, modifier = Modifier.fillMaxWidth().height(52.dp).focusRequester(tile), shape = RoundedCornerShape(12.dp), scale = 1.02f) {
                Box(Modifier.fillMaxSize().padding(horizontal = 16.dp), contentAlignment = Alignment.CenterStart) {
                    val shown = if (secret && value.isNotEmpty()) "•".repeat(value.length.coerceAtMost(16)) else value
                    Text(shown.ifEmpty { hint }, style = MaterialTheme.typography.bodyLarge, color = if (value.isEmpty()) Gold.dim.copy(alpha = 0.6f) else Gold.text, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
        } else {
            BasicTextField(
                value = value, onValueChange = onChange, singleLine = true,
                textStyle = TextStyle(color = Gold.text, fontSize = 16.sp), cursorBrush = SolidColor(Gold.gold),
                visualTransformation = if (secret) PasswordVisualTransformation() else VisualTransformation.None,
                keyboardOptions = KeyboardOptions(keyboardType = type, imeAction = ImeAction.Done, autoCorrectEnabled = false),
                keyboardActions = KeyboardActions(onDone = {
                    back = true
                    editing = false
                }),
                modifier = Modifier.fillMaxWidth().height(52.dp).focusRequester(field)
                    .onFocusChanged { if (!it.isFocused && editing) editing = false }
                    .border(2.dp, Gold.gold, RoundedCornerShape(12.dp)).background(Gold.panel2, RoundedCornerShape(12.dp))
                    .padding(horizontal = 16.dp, vertical = 15.dp),
            )
        }
    }
    LaunchedEffect(editing) {
        if (editing) {
            delay(20)
            runCatching { field.requestFocus() }
            keyboard?.show()
        } else if (back) {
            back = false
            keyboard?.hide()
            delay(20)
            runCatching { tile.requestFocus() }
        }
    }
}

@Composable
fun AddSourceScreen(app: AppState) {
    var kind by remember { mutableStateOf(SourceKind.PORTAL) }
    var name by remember { mutableStateOf("") }
    var url by remember { mutableStateOf("http://") }
    var mac by remember { mutableStateOf("00:1A:79:") }
    var user by remember { mutableStateOf("") }
    var pass by remember { mutableStateOf("") }
    var checking by remember { mutableStateOf(false) }
    var problem by remember { mutableStateOf<String?>(null) }
    var pendingSource by remember { mutableStateOf<Source?>(null) }
    val first = remember { FocusRequester() }
    val scope = rememberCoroutineScope()

    fun build(): Source? {
        val row = when (kind) {
            SourceKind.PORTAL -> mapOf("portal" to url.trim(), "mac" to mac, "source_type" to "stalker")
            SourceKind.XTREAM -> mapOf("portal" to Sources.xtreamUrl(url.trim(), user.trim(), pass.trim()), "source_type" to "m3u", "playlist_mode" to "xtream")
            SourceKind.M3U -> mapOf("portal" to url.trim(), "source_type" to "m3u", "playlist_mode" to "m3u")
        } + ("name" to name.trim())
        return Sources.fromRow(JsonObject(row.mapValues { JsonPrimitive(it.value) }))
    }

    fun save(src: Source) {
        app.add(src)
        app.toast.value = "Server added"
        app.back()
    }

    fun check() {
        problem = null
        val src = build()
        if (src == null) {
            problem = when (kind) {
                SourceKind.PORTAL -> "Check the portal address and the MAC (like 00:1A:79:12:34:56)."
                SourceKind.XTREAM -> "Fill the server address, the username and the password."
                SourceKind.M3U -> "Check the playlist address."
            }
            return
        }
        if (kind == SourceKind.XTREAM && (user.isBlank() || pass.isBlank())) {
            problem = "Fill the username and the password."
            return
        }
        checking = true
        scope.launch {
            try {
                withTimeout(30_000) { withContext(Dispatchers.IO) { providerFor(src, app.http).categories(Media.LIVE) } }
                save(src)
            } catch (e: Exception) {
                problem = (e.message ?: "The server did not answer").let { if (it.contains("Timed out", true)) "The server did not answer in time." else it }
                pendingSource = src
            } finally {
                checking = false
            }
        }
    }

    LaunchedEffect(Unit) { runCatching { first.requestFocus() } }
    Box(Modifier.fillMaxSize()) {
        Backdrop()
        Row(Modifier.fillMaxSize().padding(horizontal = 56.dp, vertical = 36.dp)) {
            Column(Modifier.width(260.dp)) {
                Text("Add a server", style = MaterialTheme.typography.displaySmall, color = Gold.text)
                Spacer(Modifier.height(10.dp))
                Text("Choose the kind your provider gave you, then fill the details with the remote.", style = MaterialTheme.typography.bodyMedium, color = Gold.dim)
                Spacer(Modifier.height(26.dp))
                for ((i, k) in SourceKind.entries.withIndex()) {
                    Tile(
                        onClick = {
                            kind = k
                            problem = null
                            pendingSource = null
                        },
                        modifier = Modifier.fillMaxWidth().height(56.dp).then(if (i == 0) Modifier.focusRequester(first) else Modifier),
                        shape = RoundedCornerShape(14.dp), selected = kind == k, scale = 1.04f,
                    ) { focused ->
                        Row(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
                            Icon(
                                when (k) {
                                    SourceKind.PORTAL -> Ic.server
                                    SourceKind.XTREAM -> Ic.live
                                    SourceKind.M3U -> Ic.list
                                },
                                null, Modifier.size(20.dp), tint = if (kind == k || focused) Gold.gold else Gold.dim,
                            )
                            Spacer(Modifier.width(12.dp))
                            Column {
                                Text(
                                    when (k) {
                                        SourceKind.PORTAL -> "Stalker portal"
                                        SourceKind.XTREAM -> "Xtream Codes"
                                        SourceKind.M3U -> "M3U playlist"
                                    },
                                    style = MaterialTheme.typography.titleSmall, color = Gold.text,
                                )
                                Text(
                                    when (k) {
                                        SourceKind.PORTAL -> "Portal address + MAC"
                                        SourceKind.XTREAM -> "Server + username + password"
                                        SourceKind.M3U -> "A playlist link"
                                    },
                                    style = MaterialTheme.typography.bodySmall, color = Gold.dim,
                                )
                            }
                        }
                    }
                    Spacer(Modifier.height(10.dp))
                }
            }
            Spacer(Modifier.width(48.dp))
            Column(Modifier.weight(1f).fillMaxHeight().verticalScroll(rememberScrollState()).padding(top = 6.dp, end = 6.dp, start = 6.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                InputField("Name (optional)", name, { name = it }, "My server", type = KeyboardType.Text)
                when (kind) {
                    SourceKind.PORTAL -> {
                        InputField("Portal address", url, { url = it }, "http://example.com:8080/c/")
                        InputField("MAC address", mac, { mac = it.uppercase() }, "00:1A:79:12:34:56", type = KeyboardType.Ascii)
                    }
                    SourceKind.XTREAM -> {
                        InputField("Server address", url, { url = it }, "http://example.com:8080")
                        Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                            InputField("Username", user, { user = it }, "username", Modifier.weight(1f), KeyboardType.Ascii)
                            InputField("Password", pass, { pass = it }, "password", Modifier.weight(1f), KeyboardType.Password, secret = true)
                        }
                    }
                    SourceKind.M3U -> InputField("Playlist address", url, { url = it }, "http://example.com/list.m3u")
                }
                problem?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = Gold.red) }
                Row(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.CenterVertically) {
                    if (checking) {
                        Spinner(28.dp)
                        Text("Checking the server…", style = MaterialTheme.typography.bodyMedium, color = Gold.dim)
                    } else {
                        GoldButton("Save", Ic.add) { check() }
                        pendingSource?.let { s -> GoldButton("Save anyway", primary = false) { save(s) } }
                    }
                }
            }
        }
    }
}
