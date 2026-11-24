package com.k3bora.ultrastalker.tv

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
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
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.tv.material3.Icon
import androidx.tv.material3.MaterialTheme
import androidx.tv.material3.Text
import com.k3bora.ultrastalker.core.Source
import com.k3bora.ultrastalker.core.SourceKind

@Composable
fun Backdrop() {
    Box(
        Modifier.fillMaxSize().background(Gold.bg).background(
            Brush.radialGradient(listOf(Gold.gold.copy(alpha = 0.10f), Color.Transparent), center = androidx.compose.ui.geometry.Offset(160f, 40f), radius = 1100f),
        ),
    )
}

@Composable
fun HomeScreen(state: AppState) {
    val sources = state.sources
    var confirm by remember { mutableStateOf<Source?>(null) }
    val first = remember { FocusRequester() }
    val startIndex = remember(sources.size) { sources.indexOfFirst { it.key == state.lastSource() }.coerceAtLeast(0) }
    val row = rememberLazyListState(startIndex)

    Box(Modifier.fillMaxSize()) {
        Backdrop()
        Column(Modifier.fillMaxSize().padding(start = 34.dp, top = 28.dp, end = 34.dp, bottom = 24.dp)) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 14.dp), verticalAlignment = Alignment.CenterVertically) {
                Image(painterResource(R.drawable.logo), "Ultra Stalker", Modifier.height(64.dp))
                Spacer(Modifier.weight(1f))
                Text("TV  ·  V${state.version}", color = Gold.dim, style = MaterialTheme.typography.labelMedium)
            }
            Spacer(Modifier.height(30.dp))
            if (sources.isEmpty()) {
                Welcome(state, first)
            } else {
                Row(verticalAlignment = Alignment.Bottom, modifier = Modifier.padding(start = 14.dp)) {
                    Text("Your servers", style = MaterialTheme.typography.headlineSmall, color = Gold.text)
                    Spacer(Modifier.width(12.dp))
                    Text("${sources.size}", style = MaterialTheme.typography.titleMedium, color = Gold.gold, modifier = Modifier.padding(bottom = 2.dp))
                }
                Spacer(Modifier.height(4.dp))
                Text("Hold OK on a server to remove it", style = MaterialTheme.typography.bodySmall, color = Gold.dim, modifier = Modifier.padding(start = 14.dp))
                Spacer(Modifier.height(14.dp))
                LazyRow(state = row, horizontalArrangement = Arrangement.spacedBy(18.dp), contentPadding = PaddingValues(vertical = 16.dp, horizontal = 18.dp)) {
                    itemsIndexed(sources, key = { _, s -> s.key }) { i, s ->
                        SourceCard(
                            s, i,
                            Modifier.then(if (i == startIndex) Modifier.focusRequester(first) else Modifier),
                            onClick = {
                                state.rememberSource(s)
                                state.go(Screen.Browse(s))
                            },
                            onLong = { confirm = s },
                        )
                    }
                }
                Spacer(Modifier.height(18.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(18.dp), modifier = Modifier.padding(horizontal = 18.dp)) {
                    ActionCard("Add a server", "Portal, Xtream or M3U", Ic.add) { state.go(Screen.AddSource) }
                    ActionCard("Restore a backup", "From your phone with a QR code", Ic.phone) { state.go(Screen.Restore) }
                }
            }
        }
        LaunchedEffect(Unit) { runCatching { first.requestFocus() } }
        confirm?.let { s ->
            Confirm(
                title = "Remove ${s.title(sources.indexOf(s))}?",
                text = "It is removed from this TV only.",
                yes = "Remove",
                onYes = {
                    state.remove(s)
                    confirm = null
                    state.toast.value = "Server removed"
                },
                onNo = { confirm = null },
            )
        }
    }
}

@Composable
private fun Welcome(state: AppState, first: FocusRequester) {
    Column(Modifier.fillMaxWidth().padding(top = 20.dp, start = 14.dp), horizontalAlignment = Alignment.Start) {
        Text("Welcome", style = MaterialTheme.typography.displaySmall, color = Gold.text)
        Spacer(Modifier.height(8.dp))
        Text("Add a server, or bring your servers from the receiver's backup with your phone.", style = MaterialTheme.typography.bodyLarge, color = Gold.dim)
        Spacer(Modifier.height(30.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(18.dp)) {
            ActionCard("Restore a backup", "From your phone with a QR code", Ic.phone, Modifier.focusRequester(first)) { state.go(Screen.Restore) }
            ActionCard("Add a server", "Portal, Xtream or M3U", Ic.add) { state.go(Screen.AddSource) }
        }
    }
}

@Composable
private fun SourceCard(s: Source, index: Int, modifier: Modifier, onClick: () -> Unit, onLong: () -> Unit) {
    Tile(onClick = onClick, onLongClick = onLong, modifier = modifier.width(250.dp).height(150.dp), scale = 1.06f) { focused ->
        Box(Modifier.fillMaxSize()) {
            if (focused) Box(Modifier.fillMaxSize().background(Brush.linearGradient(listOf(Gold.gold.copy(alpha = 0.16f), Color.Transparent))))
            Column(Modifier.fillMaxSize().padding(18.dp)) {
                Box(
                    Modifier.size(40.dp).clip(CircleShape).background(if (focused) Gold.gold else Gold.gold.copy(alpha = 0.14f)),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        when (s.kind) {
                            SourceKind.PORTAL -> Ic.server
                            SourceKind.XTREAM -> Ic.live
                            SourceKind.M3U -> Ic.list
                        },
                        null, Modifier.size(22.dp), tint = if (focused) Color.Black else Gold.gold,
                    )
                }
                Spacer(Modifier.weight(1f))
                Text(s.title(index), style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis, color = Gold.text)
                Spacer(Modifier.height(4.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Chip(s.kindLabel)
                    Spacer(Modifier.width(8.dp))
                    Text(if (s.kind == SourceKind.PORTAL) s.mac else s.host, style = MaterialTheme.typography.bodySmall, color = Gold.dim, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
        }
    }
}

@Composable
fun ActionCard(title: String, sub: String, icon: ImageVector, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Tile(onClick = onClick, modifier = modifier.width(300.dp).height(84.dp), scale = 1.05f) { focused ->
        Row(Modifier.fillMaxSize().padding(horizontal = 18.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(44.dp).clip(RoundedCornerShape(12.dp)).background(if (focused) Gold.gold else Gold.gold.copy(alpha = 0.12f)), contentAlignment = Alignment.Center) {
                Icon(icon, null, Modifier.size(24.dp), tint = if (focused) Color.Black else Gold.gold)
            }
            Spacer(Modifier.width(14.dp))
            Column {
                Text(title, style = MaterialTheme.typography.titleMedium, color = Gold.text)
                Text(sub, style = MaterialTheme.typography.bodySmall, color = Gold.dim, maxLines = 1)
            }
        }
    }
}

/* a small question in its own window (the remote can't wander behind it; Back closes it) */
@Composable
fun Confirm(title: String, text: String, yes: String, no: String = "Cancel", yesIcon: ImageVector? = Ic.delete, onYes: () -> Unit, onNo: () -> Unit) {
    val fr = remember { FocusRequester() }
    Dialog(onDismissRequest = onNo, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Column(
            Modifier.width(460.dp).clip(RoundedCornerShape(20.dp)).background(Gold.panel).padding(28.dp),
        ) {
            Text(title, style = MaterialTheme.typography.titleLarge, color = Gold.text)
            Spacer(Modifier.height(8.dp))
            Text(text, style = MaterialTheme.typography.bodyMedium, color = Gold.dim)
            Spacer(Modifier.height(24.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                GoldButton(no, primary = false, modifier = Modifier.focusRequester(fr), onClick = onNo)
                GoldButton(yes, yesIcon, onClick = onYes)
            }
        }
        LaunchedEffect(Unit) { runCatching { fr.requestFocus() } }
    }
}
