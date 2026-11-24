package com.k3bora.ultrastalker.tv

import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.tv.material3.MaterialTheme
import androidx.tv.material3.Typography
import androidx.tv.material3.darkColorScheme

/* Black and gold, like the website and the Windows program. */
object Gold {
    val bg = Color(0xFF07070A)
    val panel = Color(0xFF111116)
    val panel2 = Color(0xFF17171E)
    val line = Color(0x1FFFFFFF)
    val text = Color(0xFFF4F1EA)
    val dim = Color(0xFF9C978D)
    val gold = Color(0xFFE2B857)
    val goldLight = Color(0xFFF6DA8C)
    val goldDeep = Color(0xFFB0832B)
    val red = Color(0xFFE5484D)
    val green = Color(0xFF3DD68C)
    val shine = Brush.linearGradient(listOf(goldLight, gold, goldDeep))
    val fade = Brush.verticalGradient(listOf(Color.Transparent, bg.copy(alpha = 0.85f), bg))
    val side = Brush.horizontalGradient(listOf(bg, bg.copy(alpha = 0.92f), bg.copy(alpha = 0.35f), Color.Transparent))
}

private val type = Typography(
    displaySmall = TextStyle(fontSize = 34.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.5).sp),
    headlineSmall = TextStyle(fontSize = 24.sp, fontWeight = FontWeight.SemiBold),
    titleLarge = TextStyle(fontSize = 20.sp, fontWeight = FontWeight.SemiBold),
    titleMedium = TextStyle(fontSize = 16.sp, fontWeight = FontWeight.SemiBold),
    titleSmall = TextStyle(fontSize = 14.sp, fontWeight = FontWeight.Medium),
    bodyLarge = TextStyle(fontSize = 16.sp),
    bodyMedium = TextStyle(fontSize = 14.sp),
    bodySmall = TextStyle(fontSize = 12.sp),
    labelLarge = TextStyle(fontSize = 14.sp, fontWeight = FontWeight.SemiBold),
    labelMedium = TextStyle(fontSize = 12.sp, fontWeight = FontWeight.Medium),
    labelSmall = TextStyle(fontSize = 11.sp, fontWeight = FontWeight.Medium, letterSpacing = 0.6.sp),
)

@Composable
fun UltraTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = Gold.gold, onPrimary = Color.Black, secondary = Gold.goldLight, background = Gold.bg, onBackground = Gold.text,
            surface = Gold.panel, onSurface = Gold.text, surfaceVariant = Gold.panel2, onSurfaceVariant = Gold.dim, border = Gold.gold, error = Gold.red,
        ),
        typography = type,
        content = content,
    )
}
