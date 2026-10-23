// Writes a QR code PNG for a text (macOS, no packages needed):
//   swift firmware/tools/qr_png.swift "MCPOP1:MC-26EA:…" label.png
import AppKit
import CoreImage

let args = CommandLine.arguments
guard args.count == 3 else {
    FileHandle.standardError.write("usage: qr_png.swift <text> <out.png>\n".data(using: .utf8)!)
    exit(2)
}
guard let filter = CIFilter(name: "CIQRCodeGenerator") else { exit(1) }
filter.setValue(args[1].data(using: .utf8), forKey: "inputMessage")
filter.setValue("M", forKey: "inputCorrectionLevel")
guard let qr = filter.outputImage else { exit(1) }

// scale up with hard edges and add a white quiet zone: phone cameras need it
let scaled = qr.transformed(by: CGAffineTransform(scaleX: 12, y: 12))
let border: CGFloat = 48
let size = NSSize(width: scaled.extent.width + 2 * border, height: scaled.extent.height + 2 * border)
let image = NSImage(size: size)
image.lockFocus()
NSColor.white.setFill()
NSRect(origin: .zero, size: size).fill()
NSGraphicsContext.current?.imageInterpolation = .none
NSBitmapImageRep(ciImage: scaled).draw(in: NSRect(x: border, y: border, width: scaled.extent.width, height: scaled.extent.height))
image.unlockFocus()

guard let tiff = image.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
      let png = rep.representation(using: .png, properties: [:]) else { exit(1) }
try png.write(to: URL(fileURLWithPath: args[2]))
print("wrote \(args[2]) (\(Int(size.width))x\(Int(size.height)))")
