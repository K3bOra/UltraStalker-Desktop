import org.jetbrains.kotlin.gradle.dsl.JvmTarget

/* The relay and the local server: plain Kotlin (no Android), so it is tested on the
   build machine and runs unchanged on the TV. */
plugins {
    kotlin("jvm")
    `java-library`
}
java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
kotlin {
    compilerOptions { jvmTarget.set(JvmTarget.JVM_17) }
}
dependencies {
    api("com.squareup.okhttp3:okhttp:4.12.0")
    api("org.nanohttpd:nanohttpd:2.3.1")
    api("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    testImplementation(kotlin("test"))
    testImplementation("junit:junit:4.13.2")
}
tasks.test {
    useJUnit()
    testLogging { events("passed", "failed"); exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL }
}
/* "gradle :relay:serve -Pweb=<folder with web/ and app/>": the TV's server on a computer,
   for the browser tests of the remote-control navigation. */
tasks.register<JavaExec>("serve") {
    classpath = sourceSets["main"].runtimeClasspath
    mainClass.set("com.k3bora.ultrastalker.relay.ServeKt")
    args = listOf((project.findProperty("web") ?: "../build/site").toString(), (project.findProperty("port") ?: "47450").toString())
}
