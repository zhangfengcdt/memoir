// Mock data generation for demo mode

function generateMockTree(density = 1.0) {
    // Generate comprehensive tree with 118 total memories at full density
    return {
        // Personal (26 memories)
        'profile.personal.identity': Math.floor(8 * density),
        'profile.personal.location': Math.floor(6 * density),
        'profile.personal.relationships': Math.floor(5 * density),
        'profile.personal.health': Math.floor(4 * density),
        'profile.personal.goals': Math.floor(3 * density),

        // Professional (34 memories)
        'profile.professional.skills': Math.floor(12 * density),
        'profile.professional.experience': Math.floor(9 * density),
        'profile.professional.companies': Math.floor(4 * density),
        'profile.professional.education': Math.floor(3 * density),
        'profile.professional.achievements': Math.floor(6 * density),

        // Preferences (14 memories)
        'profile.preferences.interface': Math.floor(5 * density),
        'profile.preferences.notifications': Math.floor(3 * density),
        'profile.preferences.privacy': Math.floor(4 * density),
        'profile.preferences.workflow': Math.floor(2 * density),

        // Interests (21 memories)
        'profile.interests.music': Math.floor(4 * density),
        'profile.interests.books': Math.floor(7 * density),
        'profile.interests.movies': Math.floor(3 * density),
        'profile.interests.sports': Math.floor(2 * density),
        'profile.interests.hobbies': Math.floor(5 * density),

        // Technology (17 memories)
        'profile.technology.devices': Math.floor(3 * density),
        'profile.technology.tools': Math.floor(8 * density),
        'profile.technology.platforms': Math.floor(6 * density)
    };
}

// Mock data and interactions with 30 commits
const commits = {
    'f9a8b12': { tree: generateMockTree(1.0) },  // Latest - full data
    'd75e832': { tree: generateMockTree(0.98) },
    'e2c4f89': { tree: generateMockTree(0.95) },
    'b3a7c91': { tree: generateMockTree(0.93) },
    'c3f7921': { tree: generateMockTree(0.90) },
    'a9e5d21': { tree: generateMockTree(0.88) },
    'b92f381': { tree: generateMockTree(0.85) }, // v2.3.0
    '7f2a8b3': { tree: generateMockTree(0.82) },
    '6e1b4c7': { tree: generateMockTree(0.80) },
    'a4f7f14': { tree: generateMockTree(0.78) },
    '3d9c2e8': { tree: generateMockTree(0.75) },
    '8e1c492': { tree: generateMockTree(0.72) }, // v2.2.0
    '5a8f3b1': { tree: generateMockTree(0.70) },
    '2b7e4a9': { tree: generateMockTree(0.67) },
    '9c4d1f8': { tree: generateMockTree(0.65) },
    'f3e8a72': { tree: generateMockTree(0.62) },
    '35be3ae': { tree: generateMockTree(0.60) }, // v2.1.0
    '1a5c9d4': { tree: generateMockTree(0.57) },
    '8b2f6e3': { tree: generateMockTree(0.55) },
    '4d7a3c1': { tree: generateMockTree(0.52) },
    '6f8e2b9': { tree: generateMockTree(0.50) },
    '9e4b7a2': { tree: generateMockTree(0.47) },
    '2c1e5f7': { tree: generateMockTree(0.45) }, // v2.0.0
    '7a3d8c4': { tree: generateMockTree(0.42) },
    '5b9f2e1': { tree: generateMockTree(0.40) },
    '8c4a6f3': { tree: generateMockTree(0.35) }, // v1.5.0
    '3f7b1a8': { tree: generateMockTree(0.30) },
    '00c5625': { tree: generateMockTree(0.20) }  // v1.0.0 - minimal data
};

// Export for other modules
window.mockData = {
    generateMockTree,
    commits
};