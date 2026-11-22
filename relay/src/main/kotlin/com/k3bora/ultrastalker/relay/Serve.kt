package com.k3bora.ultrastalker.relay

import java.io.File

/* The TV's local server on a computer (tests): serve <folder>/web and <folder>/app. */
fun main(args: Array<String>) {
    val root = File(args.getOrElse(0) { "build/site" })
    val port = args.getOrElse(1) { "47450" }.toInt()
    val server = LocalServer(port, FolderSource(root), "test")
    server.start(5000, false)
    println("SERVING ${server.origin}")
    Thread.currentThread().join()
}
