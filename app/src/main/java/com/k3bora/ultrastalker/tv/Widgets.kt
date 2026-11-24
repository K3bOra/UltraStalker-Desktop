package com.k3bora.ultrastalker.tv

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
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
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.tv.material3.Border
import androidx.tv.material3.ClickableSurfaceDefaults
import androidx.tv.material3.Glow
import androidx.tv.material3.Icon
import androidx.tv.material3.MaterialTheme
import androidx.tv.material3.Surface
import androidx.tv.material3.Text
import coil.compose.SubcomposeAsyncImage
import kotlinx.coroutines.delay

/* ------------------------------------------------------------------ icons (Material, 24×24) */
object Ic {
    private fun icon(name: String, d: String) = ImageVector.Builder(name, 24.dp, 24.dp, 24f, 24f)
        .addPath(PathParser().parsePathString(d).toNodes(), fill = SolidColor(Color.White)).build()

    val play = icon("play", "M8,5v14l11,-7z")
    val pause = icon("pause", "M6,19h4L10,5L6,5v14zM14,5v14h4L18,5h-4z")
    val add = icon("add", "M19,13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z")
    val live = icon("live", "M21,6h-7.59l3.29,-3.29L16,2l-4,4 -4,-4 -0.71,0.71L10.59,6L3,6c-1.1,0 -2,0.89 -2,2v12c0,1.1 0.9,2 2,2h18c1.1,0 2,-0.9 2,-2L23,8c0,-1.11 -0.9,-2 -2,-2zM21,20L3,20L3,8h18v12zM9,10v8l7,-4z")
    val movie = icon("movie", "M18,4l2,4h-3l-2,-4h-2l2,4h-3l-2,-4H8l2,4H7L5,4H4c-1.1,0 -1.99,0.9 -1.99,2L2,18c0,1.1 0.9,2 2,2h16c1.1,0 2,-0.9 2,-2V4h-4z")
    val series = icon("series", "M4,6H2v14c0,1.1 0.9,2 2,2h14v-2H4V6zM20,2H8c-1.1,0 -2,0.9 -2,2v12c0,1.1 0.9,2 2,2h12c1.1,0 2,-0.9 2,-2V4c0,-1.1 -0.9,-2 -2,-2zM12,14.5v-9l6,4.5 -6,4.5z")
    val phone = icon("phone", "M17,1.01L7,1c-1.1,0 -2,0.9 -2,2v18c0,1.1 0.9,2 2,2h10c1.1,0 2,-0.9 2,-2V3c0,-1.1 -0.9,-1.99 -2,-1.99zM17,19H7V5h10v14z")
    val rewind = icon("rewind", "M11,18V6l-8.5,6 8.5,6zM11.5,12l8.5,6V6l-8.5,6z")
    val forward = icon("forward", "M4,18l8.5,-6L4,6v12zM13,6v12l8.5,-6L13,6z")
    val audio = icon("audio", "M12,3v9.28c-0.47,-0.17 -0.97,-0.28 -1.5,-0.28C8.01,12 6,14.01 6,16.5S8.01,21 10.5,21c2.31,0 4.2,-1.75 4.45,-4H15V6h4V3h-7z")
    val subtitles = icon("subtitles", "M20,4H4c-1.1,0 -2,0.9 -2,2v12c0,1.1 0.9,2 2,2h16c1.1,0 2,-0.9 2,-2V6c0,-1.1 -0.9,-2 -2,-2zM4,12h4v2H4v-2zM14,18H4v-2h10v2zM20,18h-4v-2h4v2zM20,14H10v-2h10v2z")
    val aspect = icon("aspect", "M19,12h-2v3h-3v2h5v-5zM7,9h3L10,7L5,7v5h2L7,9zM21,3L3,3c-1.1,0 -2,0.9 -2,2v14c0,1.1 0.9,2 2,2h18c1.1,0 2,-0.9 2,-2L23,5c0,-1.1 -0.9,-2 -2,-2zM21,19.01L3,19.01L3,4.99h18v14.02z")
    val delete = icon("delete", "M6,19c0,1.1 0.9,2 2,2h8c1.1,0 2,-0.9 2,-2V7H6v12zM19,4h-3.5l-1,-1h-5l-1,1H5v2h14V4z")
    val next = icon("next", "M6,18l8.5,-6L6,6v12zM16,6v12h2V6h-2z")
    val star = icon("star", "M12,17.27L18.18,21l-1.64,-7.03L22,9.24l-7.19,-0.61L12,2 9.19,8.63 2,9.24l5.46,4.73L5.82,21z")
    val folder = icon("folder", "M20,6h-8l-2,-2H4c-1.1,0 -1.99,0.9 -1.99,2L2,18c0,1.1 0.9,2 2,2h16c1.1,0 2,-0.9 2,-2V8c0,-1.1 -0.9,-2 -2,-2zM20,18H4V8h16v10z")
    val server = icon("server", "M20,13H4c-0.55,0 -1,0.45 -1,1v6c0,0.55 0.45,1 1,1h16c0.55,0 1,-0.45 1,-1v-6c0,-0.55 -0.45,-1 -1,-1zM7,19c-1.1,0 -2,-0.9 -2,-2s0.9,-2 2,-2 2,0.9 2,2 -0.9,2 -2,2zM20,3H4c-0.55,0 -1,0.45 -1,1v6c0,0.55 0.45,1 1,1h16c0.55,0 1,-0.45 1,-1V4c0,-0.55 -0.45,-1 -1,-1zM7,9c-1.1,0 -2,-0.9 -2,-2s0.9,-2 2,-2 2,0.9 2,2 -0.9,2 -2,2z")
    val list = icon("list", "M3,13h2v-2H3v2zM3,17h2v-2H3v2zM3,9h2V7H3v2zM7,13h14v-2H7v2zM7,17h14v-2H7v2zM7,7v2h14V7H7z")
    val retry = icon("retry", "M17.65,6.35C16.2,4.9 14.21,4 12,4c-4.42,0 -7.99,3.58 -7.99,8s3.57,8 7.99,8c3.73,0 6.84,-2.55 7.73,-6h-2.08c-0.82,2.33 -3.04,4 -5.65,4 -3.31,0 -6,-2.69 -6,-6s2.69,-6 6,-6c1.66,0 3.14,0.69 4.22,1.78L13,11h7V4l-2.35,2.35z")
}

fun mediaIcon(m: com.k3bora.ultrastalker.core.Media) = when (m) {
    com.k3bora.ultrastalker.core.Media.LIVE -> Ic.live
    com.k3bora.ultrastalker.core.Media.MOVIES -> Ic.movie
    com.k3bora.ultrastalker.core.Media.SERIES -> Ic.series
}

fun mediaLabel(m: com.k3bora.ultrastalker.core.Media) = when (m) {
    com.k3bora.ultrastalker.core.Media.LIVE -> "Live TV"
    com.k3bora.ultrastalker.core.Media.MOVIES -> "Movies"
    com.k3bora.ultrastalker.core.Media.SERIES -> "Series"
}

/* ------------------------------------------------------------------ focusable tiles */
@Composable
fun Tile(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    shape: RoundedCornerShape = RoundedCornerShape(14.dp),
    scale: Float = 1.04f,
    selected: Boolean = false,
    onLongClick: (() -> Unit)? = null,
    content: @Composable (focused: Boolean) -> Unit,
) {
    var focused by remember { mutableStateOf(false) }
    Surface(
        onClick = onClick,
        onLongClick = onLongClick,
        modifier = modifier.onFocusChanged { focused = it.isFocused || it.hasFocus },
        shape = ClickableSurfaceDefaults.shape(shape),
        scale = ClickableSurfaceDefaults.scale(focusedScale = scale),
        colors = ClickableSurfaceDefaults.colors(
            containerColor = if (selected) Gold.gold.copy(alpha = 0.13f) else Gold.panel,
            contentColor = Gold.text,
            focusedContainerColor = Gold.panel2,
            focusedContentColor = Gold.text,
            pressedContainerColor = Gold.panel2,
        ),
        border = ClickableSurfaceDefaults.border(
            border = Border(BorderStroke(1.dp, if (selected) Gold.gold.copy(alpha = 0.55f) else Gold.line), shape = shape),
            focusedBorder = Border(BorderStroke(2.5.dp, Gold.gold), shape = shape),
        ),
        glow = ClickableSurfaceDefaults.glow(focusedGlow = Glow(Gold.gold.copy(alpha = 0.35f), 14.dp)),
    ) { content(focused) }
}

@Composable
fun GoldButton(text: String, icon: ImageVector? = null, modifier: Modifier = Modifier, primary: Boolean = true, onClick: () -> Unit) {
    val shape = RoundedCornerShape(50)
    Surface(
        onClick = onClick,
        modifier = modifier.height(48.dp),
        shape = ClickableSurfaceDefaults.shape(shape),
        scale = ClickableSurfaceDefaults.scale(focusedScale = 1.06f),
        colors = ClickableSurfaceDefaults.colors(
            containerColor = if (primary) Gold.gold.copy(alpha = 0.16f) else Gold.panel,
            contentColor = if (primary) Gold.goldLight else Gold.text,
            focusedContainerColor = Gold.gold,
            focusedContentColor = Color.Black,
        ),
        border = ClickableSurfaceDefaults.border(
            border = Border(BorderStroke(1.dp, if (primary) Gold.gold.copy(alpha = 0.6f) else Gold.line), shape = shape),
            focusedBorder = Border(BorderStroke(2.dp, Gold.goldLight), shape = shape),
        ),
        glow = ClickableSurfaceDefaults.glow(focusedGlow = Glow(Gold.gold.copy(alpha = 0.45f), 12.dp)),
    ) {
        Row(Modifier.fillMaxHeight().padding(horizontal = 22.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.Center) {
            if (icon != null) {
                Icon(icon, null, Modifier.size(22.dp))
                if (text.isNotEmpty()) Spacer(Modifier.width(10.dp))
            }
            if (text.isNotEmpty()) Text(text, style = MaterialTheme.typography.labelLarge, maxLines = 1)
        }
    }
}

/* ------------------------------------------------------------------ pictures */
@Composable
fun Picture(url: String, title: String, modifier: Modifier = Modifier, fit: ContentScale = ContentScale.Crop, letters: Dp = 28.dp) {
    val fallback: @Composable () -> Unit = {
        Box(Modifier.fillMaxSize().background(Gold.panel2), contentAlignment = Alignment.Center) {
            Text(
                initials(title), color = Gold.gold.copy(alpha = 0.75f), fontWeight = FontWeight.Bold,
                fontSize = (letters.value * 0.75f).sp, textAlign = TextAlign.Center,
            )
        }
    }
    if (url.isEmpty()) Box(modifier) { fallback() }
    else SubcomposeAsyncImage(
        model = url, contentDescription = null, modifier = modifier, contentScale = fit,
        loading = { fallback() }, error = { fallback() },
    )
}

fun initials(t: String): String {
    val w = t.replace(Regex("[^\\p{L}\\p{N} ]"), " ").split(" ").filter { it.isNotBlank() }
    return when {
        w.isEmpty() -> "•"
        w.size == 1 -> w[0].take(2).uppercase()
        else -> (w[0].take(1) + w[1].take(1)).uppercase()
    }
}

/* ------------------------------------------------------------------ states */
@Composable
fun Loading(modifier: Modifier = Modifier, label: String = "") {
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        Spinner()
        if (label.isNotEmpty()) {
            Spacer(Modifier.height(14.dp))
            Text(label, color = Gold.dim, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
fun Spinner(size: Dp = 40.dp) {
    var turn by remember { mutableStateOf(0f) }
    LaunchedEffect(Unit) {
        while (true) {
            androidx.compose.animation.core.withInfiniteAnimationFrameMillis { turn = (it % 1000L) / 1000f * 360f }
        }
    }
    Canvas(Modifier.size(size)) {
        drawArc(Gold.line, 0f, 360f, false, style = Stroke(4.dp.toPx()))
        drawArc(Gold.gold, turn, 100f, false, style = Stroke(4.dp.toPx(), cap = androidx.compose.ui.graphics.StrokeCap.Round))
    }
}

@Composable
fun Problem(message: String, modifier: Modifier = Modifier, focus: Boolean = true, retry: (() -> Unit)?) {
    val fr = remember { FocusRequester() }
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        Text("Something went wrong", style = MaterialTheme.typography.titleLarge, color = Gold.text)
        Spacer(Modifier.height(8.dp))
        Text(message, style = MaterialTheme.typography.bodyMedium, color = Gold.dim, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth(0.7f))
        if (retry != null) {
            Spacer(Modifier.height(22.dp))
            GoldButton("Try again", Ic.retry, Modifier.focusRequester(fr), onClick = retry)
            if (focus) LaunchedEffect(Unit) { runCatching { fr.requestFocus() } }
        }
    }
}

@Composable
fun Empty(text: String, modifier: Modifier = Modifier) {
    Box(modifier, contentAlignment = Alignment.Center) { Text(text, color = Gold.dim, style = MaterialTheme.typography.bodyLarge) }
}

@Composable
fun ToastHost(state: AppState) {
    val msg = state.toast.value
    LaunchedEffect(msg) {
        if (msg != null) {
            delay(3200)
            state.toast.value = null
        }
    }
    Box(Modifier.fillMaxSize().padding(bottom = 40.dp), contentAlignment = Alignment.BottomCenter) {
        AnimatedVisibility(msg != null, enter = fadeIn(), exit = fadeOut()) {
            Box(
                Modifier.clip(RoundedCornerShape(50)).background(Color(0xEE16161C)).padding(PaddingValues(horizontal = 26.dp, vertical = 14.dp)),
            ) { Text(msg ?: "", color = Gold.text, style = MaterialTheme.typography.titleSmall, maxLines = 2, overflow = TextOverflow.Ellipsis) }
        }
    }
}

@Composable
fun Chip(text: String, color: Color = Gold.gold) {
    Box(Modifier.clip(RoundedCornerShape(6.dp)).background(color.copy(alpha = 0.14f)).padding(horizontal = 8.dp, vertical = 3.dp)) {
        Text(text, color = color, style = MaterialTheme.typography.labelSmall, maxLines = 1)
    }
}
