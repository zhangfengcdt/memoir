// UI Helpers - Notification system and utility functions

// Initialize notification styles
function initializeNotificationStyles() {
    // Add CSS animation styles for notifications
    if (!document.querySelector('#notification-styles')) {
        const style = document.createElement('style');
        style.id = 'notification-styles';
        style.textContent = `
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            @keyframes slideOut {
                from { transform: translateX(0); opacity: 1; }
                to { transform: translateX(100%); opacity: 0; }
            }
        `;
        document.head.appendChild(style);
    }
}

// Show notification message
function showNotification(message, type = 'info', duration = 3000) {
    // Calculate position to stack notifications vertically
    const existingNotifications = document.querySelectorAll('.notification');
    let topPosition = 100;

    existingNotifications.forEach(notif => {
        const rect = notif.getBoundingClientRect();
        topPosition = Math.max(topPosition, rect.bottom + 10);
    });

    // Create notification element
    const notification = document.createElement('div');
    notification.className = 'notification';
    notification.style.cssText = `
        position: fixed;
        top: ${topPosition}px;
        right: 20px;
        padding: 12px 20px;
        background: ${type === 'error' ? '#ef4444' : type === 'success' ? '#10b981' : '#3b82f6'};
        color: white;
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        z-index: 10000;
        animation: slideIn 0.3s ease;
        white-space: pre-line;
        font-family: 'JetBrains Mono', monospace;
        font-size: 12px;
        max-width: 400px;
        line-height: 1.4;
        transition: all 0.3s ease;
    `;
    notification.textContent = message;

    document.body.appendChild(notification);

    // Remove after specified duration
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => {
            notification.remove();
            // Reposition remaining notifications
            repositionNotifications();
        }, 300);
    }, duration);
}

// Reposition notifications when one is removed
function repositionNotifications() {
    const notifications = document.querySelectorAll('.notification');
    let topPosition = 100;

    notifications.forEach(notif => {
        notif.style.top = `${topPosition}px`;
        const rect = notif.getBoundingClientRect();
        topPosition = rect.bottom + 10;
    });
}

// Initialize styles when DOM is loaded
document.addEventListener('DOMContentLoaded', initializeNotificationStyles);

// Export to global scope for backward compatibility
window.showNotification = showNotification;
window.repositionNotifications = repositionNotifications;
window.initializeNotificationStyles = initializeNotificationStyles;
