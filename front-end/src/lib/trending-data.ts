export type TrendingTag = {
  tag: string;
  category: string;
  heat_score: number;
  description: string;
  signals: string[];
};

export type TrendPost = {
  id: string;
  author: string;
  handle: string;
  views: string;
  time_ago: string;
  caption: string;
  image_url: string;
  tags: string[];
};

export type TrendDetails = {
  tag_name: string;
  hero_url: string;
  about_trend: string;
  posts: TrendPost[];
};

export const TRENDING_FEED: TrendingTag[] = [
  {
    tag: "#WorldCupFinal",
    category: "sports",
    heat_score: 97,
    description: "India vs Australia final match discussion",
    signals: ["अत्यधिक उपयोग", "अत्यधिक खोजा गया", "बहुत लोकप्रिय"],
  },
  {
    tag: "#सदाबहारहिंदीगाने",
    category: "music",
    heat_score: 92,
    description: "किशोर कुमार और लता मंगेशकर के सदाबहार गाने",
    signals: ["अत्यधिक उपयोग", "बहुत लोकप्रिय"],
  },
  {
    tag: "#WeddingSeason",
    category: "lifestyle",
    heat_score: 88,
    description: "Bridal looks, mehendi designs and shaadi vibes",
    signals: ["तेज़ी से बढ़ रहा", "अत्यधिक खोजा गया"],
  },
  {
    tag: "#MonsoonVibes",
    category: "weather",
    heat_score: 85,
    description: "बारिश के मौसम में चाय, पकौड़े और यादें",
    signals: ["तेज़ी से बढ़ रहा"],
  },
  {
    tag: "#BollywoodBuzz",
    category: "entertainment",
    heat_score: 81,
    description: "Latest Bollywood news, releases and gossip",
    signals: ["अत्यधिक उपयोग", "बहुत लोकप्रिय"],
  },
  {
    tag: "#StreetFoodIndia",
    category: "food",
    heat_score: 76,
    description: "गोलगप्पे, चाट और देसी ज़ायका",
    signals: ["अत्यधिक खोजा गया"],
  },
  {
    tag: "#TechTuesday",
    category: "technology",
    heat_score: 72,
    description: "New gadgets, AI updates and smartphone launches",
    signals: ["तेज़ी से बढ़ रहा"],
  },
  {
    tag: "#FitnessGoals",
    category: "health",
    heat_score: 68,
    description: "Yoga, gym aur healthy lifestyle tips",
    signals: ["बहुत लोकप्रिय"],
  },
  {
    tag: "#T20CricketCarnival",
    category: "sports",
    heat_score: 64,
    description: "T20 league highlights, scores and fan reactions",
    signals: ["तेज़ी से बढ़ रहा", "अत्यधिक उपयोग"],
  },
  {
    tag: "#SummerSpecial",
    category: "lifestyle",
    heat_score: 59,
    description: "गर्मी में ठंडक देने वाले रेसिपीज़ और टिप्स",
    signals: ["अत्यधिक खोजा गया"],
  },
  {
    tag: "#DesiMemes",
    category: "entertainment",
    heat_score: 55,
    description: "हँसी के पटाखे — रोज़ाना के देसी memes",
    signals: ["बहुत लोकप्रिय"],
  },
];

const SAMPLE_POSTS: TrendPost[] = [
  {
    id: "p1",
    author: "Cricket Junkie",
    handle: "@cricketjunkie",
    views: "24K",
    time_ago: "2 घंटे पहले",
    caption: "क्या मैच था! Last over thriller — दिल थाम के बैठे रहे पूरा परिवार 🏏🔥",
    image_url:
      "https://images.unsplash.com/photo-1531415074968-036ba1b575da?w=900&q=80",
    tags: ["#WorldCupFinal", "#TeamIndia"],
  },
  {
    id: "p2",
    author: "Desi Updates",
    handle: "@desiupdates",
    views: "18K",
    time_ago: "5 घंटे पहले",
    caption: "Champions once again 🇮🇳 Virat और Rohit ने इतिहास रच दिया।",
    image_url:
      "https://images.unsplash.com/photo-1540747913346-19e32dc3e97e?w=900&q=80",
    tags: ["#WorldCupFinal"],
  },
  {
    id: "p3",
    author: "Sports Bytes",
    handle: "@sportsbytes",
    views: "12K",
    time_ago: "8 घंटे पहले",
    caption: "Bumrah की वो yorker — पूरा stadium खड़ा हो गया था!",
    image_url:
      "https://images.unsplash.com/photo-1593341646782-e0b495cff86d?w=900&q=80",
    tags: ["#WorldCupFinal", "#Bumrah"],
  },
  {
    id: "p4",
    author: "Fan Moments",
    handle: "@fanmoments",
    views: "9.5K",
    time_ago: "10 घंटे पहले",
    caption: "Trophy uthate hi पूरे देश में जश्न शुरू! 🏆🎉 #ProudIndian",
    image_url:
      "https://images.unsplash.com/photo-1624880357913-a8539238245b?w=900&q=80",
    tags: ["#WorldCupFinal", "#ProudIndian"],
  },
];

export function getTrendingFeed(): Promise<TrendingTag[]> {
  return new Promise((resolve) => setTimeout(() => resolve(TRENDING_FEED), 250));
}

export function getTrendDetails(tagName: string): Promise<TrendDetails> {
  const decoded = decodeURIComponent(tagName);
  const match =
    TRENDING_FEED.find((t) => t.tag === decoded) ?? TRENDING_FEED[0];
  return new Promise((resolve) =>
    setTimeout(
      () =>
        resolve({
          tag_name: match.tag,
          hero_url: `https://images.unsplash.com/photo-1540747913346-19e32dc3e97e?w=1400&q=80`,
          about_trend: `${match.description}. यह ट्रेंड पिछले कुछ घंटों में तेज़ी से ऊपर आया है और लाखों यूज़र्स ने इस पर पोस्ट, वीडियो और कमेंट्स शेयर किए हैं। ${match.tag} पर सबसे ज़्यादा engagement ${match.category} category से आ रहा है।`,
          posts: SAMPLE_POSTS,
        }),
      200
    )
  );
}

export function getRankFor(tag: string): number {
  const i = TRENDING_FEED.findIndex((t) => t.tag === tag);
  return i === -1 ? 1 : i + 1;
}
