import CoreGraphics
import Foundation
import ImageIO
import Vision

struct ImageRequest: Decodable {
    let id: String
    let data: String
}

struct TextLine: Encodable {
    let text: String
    let box: [Double]
    let confidence: Float
}

struct OCRReply: Encodable {
    let id: String
    let width: Int
    let height: Int
    let lines: [TextLine]
    let error: String?
}

func recognize(_ input: ImageRequest) -> OCRReply {
    guard let data = Data(base64Encoded: input.data) else {
        return OCRReply(id: input.id, width: 0, height: 0, lines: [], error: "invalid_base64")
    }
    guard let source = CGImageSourceCreateWithData(data as CFData, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        return OCRReply(id: input.id, width: 0, height: 0, lines: [], error: "invalid_image")
    }

    let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
    let orientationValue = (properties?[kCGImagePropertyOrientation] as? NSNumber)?.uint32Value
    let orientation = orientationValue.flatMap(CGImagePropertyOrientation.init(rawValue:)) ?? .up
    let rotated = [.left, .right, .leftMirrored, .rightMirrored].contains(orientation)
    let width = rotated ? image.height : image.width
    let height = rotated ? image.width : image.height

    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["zh-Hans", "en-US"]
    request.usesLanguageCorrection = false

    do {
        try VNImageRequestHandler(cgImage: image, orientation: orientation).perform([request])
    } catch {
        return OCRReply(id: input.id, width: width, height: height, lines: [], error: "vision_recognition_failed")
    }

    let lines = (request.results ?? []).compactMap { observation -> TextLine? in
        guard let candidate = observation.topCandidates(1).first else { return nil }
        let bounds = observation.boundingBox.intersection(CGRect(x: 0, y: 0, width: 1, height: 1))
        guard !bounds.isEmpty else { return nil }
        // Vision measures from the bottom left; the report measures from the top left.
        let box = [Double(bounds.minX), Double(1 - bounds.maxY), Double(bounds.width), Double(bounds.height)]
        return TextLine(text: candidate.string, box: box, confidence: candidate.confidence)
    }
    return OCRReply(id: input.id, width: width, height: height, lines: lines, error: nil)
}

let decoder = JSONDecoder()
let encoder = JSONEncoder()
let output = FileHandle.standardOutput

while let row = readLine() {
    let reply: OCRReply = autoreleasepool {
        guard let request = try? decoder.decode(ImageRequest.self, from: Data(row.utf8)) else {
            return OCRReply(id: "", width: 0, height: 0, lines: [], error: "invalid_request")
        }
        return recognize(request)
    }
    // Write each response directly to the pipe before waiting for the next image.
    if var data = try? encoder.encode(reply) {
        data.append(0x0A)
        output.write(data)
    }
}
