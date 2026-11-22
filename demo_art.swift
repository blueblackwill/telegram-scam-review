// Recreate the neutral teaching sheet. Run from the repository root.
import AppKit

let canvas = NSImage(size: NSSize(width: 1100, height: 700))
canvas.lockFocus()
NSColor(calibratedWhite: 0.97, alpha: 1).setFill()
NSBezierPath(rect: NSRect(x: 0, y: 0, width: 1100, height: 700)).fill()
let accent = NSColor(calibratedRed: 0.12, green: 0.35, blue: 0.29, alpha: 1)
let ink = NSColor(calibratedWhite: 0.12, alpha: 1)

func draw(_ value: String, _ y: CGFloat, _ size: CGFloat, _ color: NSColor, _ weight: NSFont.Weight) {
    (value as NSString).draw(at: NSPoint(x: 72, y: y), withAttributes: [
        .font: NSFont.systemFont(ofSize: size, weight: weight), .foregroundColor: color
    ])
}

draw("SYNTHETIC EVIDENCE  /  教学样例", 604, 30, accent, .bold)
draw("离线线索标记 · 无可操作页面", 541, 24, ink, .regular)
draw("Bot profile  /  机器人", 458, 34, ink, .semibold)
draw("Open link  /  打开链接", 382, 34, ink, .semibold)
draw("https://orders.example.invalid/test", 326, 24, accent, .regular)
draw("Payment request  /  待支付  8.00 USDT", 246, 34, ink, .semibold)
draw("Token allowance  /  代币授权", 166, 34, ink, .semibold)
draw("SIMULATED INPUT  /  没有真实交易", 68, 24, accent, .bold)
canvas.unlockFocus()
guard let tiff = canvas.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: tiff),
      let png = bitmap.representation(using: .png, properties: [:]) else {
    fatalError("Cannot render the synthetic evidence image")
}
try png.write(to: URL(fileURLWithPath: "demo.png"))
