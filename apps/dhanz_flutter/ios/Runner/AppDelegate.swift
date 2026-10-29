import Flutter
import UIKit
import UserNotifications

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    if let registrar = engineBridge.pluginRegistry.registrar(forPlugin: "DhanzPushPlugin") {
      DhanzPushPlugin.register(with: registrar)
    }
  }
}

/// Push notifications bridge for `lib/core/platform/push.dart` (channel `ai.dhanz/push`), using
/// Apple Push Notification service directly. Requires the Push Notifications capability
/// (aps-environment entitlement); without it `getToken` returns nil. See docs/RELEASE.md.
final class DhanzPushPlugin: NSObject, FlutterPlugin, UNUserNotificationCenterDelegate {
  private let channel: FlutterMethodChannel
  private var token: String?
  private var tokenWaiters: [FlutterResult] = []
  private var pendingConversation: String?
  private var dartReady = false

  init(channel: FlutterMethodChannel) {
    self.channel = channel
  }

  static func register(with registrar: FlutterPluginRegistrar) {
    let channel = FlutterMethodChannel(name: "ai.dhanz/push", binaryMessenger: registrar.messenger())
    let instance = DhanzPushPlugin(channel: channel)
    registrar.addMethodCallDelegate(instance, channel: channel)
    registrar.addApplicationDelegate(instance)
    UNUserNotificationCenter.current().delegate = instance
  }

  func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
    case "requestPermission":
      UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
        DispatchQueue.main.async {
          if granted { UIApplication.shared.registerForRemoteNotifications() }
          result(granted)
        }
      }
    case "getToken":
      if let token = token {
        result(token)
      } else {
        tokenWaiters.append(result)
        UIApplication.shared.registerForRemoteNotifications()
      }
    case "initialConversation":
      dartReady = true
      result(pendingConversation)
      pendingConversation = nil
    default:
      result(FlutterMethodNotImplemented)
    }
  }

  func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
    let hex = deviceToken.map { String(format: "%02x", $0) }.joined()
    let changed = token != nil && token != hex
    token = hex
    tokenWaiters.forEach { $0(hex) }
    tokenWaiters.removeAll()
    if changed { channel.invokeMethod("onToken", arguments: hex) }
  }

  func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
    NSLog("DHANZ AI: push registration failed: \(error.localizedDescription)")
    tokenWaiters.forEach { $0(nil) }
    tokenWaiters.removeAll()
  }

  // Show the banner even while the app is open (e.g. the answer finished in another conversation).
  func userNotificationCenter(
    _ center: UNUserNotificationCenter,
    willPresent notification: UNNotification,
    withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
  ) {
    completionHandler([.banner, .list, .sound])
  }

  func userNotificationCenter(
    _ center: UNUserNotificationCenter,
    didReceive response: UNNotificationResponse,
    withCompletionHandler completionHandler: @escaping () -> Void
  ) {
    if let id = response.notification.request.content.userInfo["conversation_id"] as? String {
      if dartReady {
        channel.invokeMethod("onNotificationTap", arguments: ["conversation_id": id])
      } else {
        pendingConversation = id // the tap launched the app; Dart asks for it once it starts
      }
    }
    completionHandler()
  }
}
