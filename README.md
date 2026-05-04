# trending_tag_system
This system is aimed to build a list of daily trending tags using Maths and LLM.

1. How the System Decides What’s Trending?
    The system doesn't just look at what is popular; it looks for growth and momentum. A topic that gets 1,000 posts every single day isn't "trending"—it's just "popular." A topic that goes from 0 to 100 posts in a short timeframe is a trend.
   I used a multi-factor scoring engine that weighs the following:
   - Velocity (The Spike): How fast is the tag growing compared to its average over the last 7 days?
   - User Intent (Search): Are people actively typing this tag into the search bar?
   - Engagement: Are people merely seeing the tag, or are they liking, sharing, and commenting on it?
   - Demographic Usecase: All data is filtered to ensure it comes from Hindi-speaking users, making the results highly local.
   - The 2-Hour "Surge" LogicTo identify a trend, the system looks at data through a 2-hour sliding window. This window moves forward every minute to keep the feed fresh.
         - How it works:The Current Snapshot: The system calculates how many times a tag was used in the last 2 hours.
         - The Baseline Comparison: It compares that number to the tag’s 7-day average (the "normal" level of activity).
         - The Velocity Check: If the activity in the last 2 hours is significantly higher than the average, the tag is flagged as "Spiking".
         - The Momentum Check: It also compares the last 2 hours against the 2 hours before that. If the numbers are still climbing, the tag gains "Momentum".
     
2. System Workflow Diagram
      The data follows a circular path to ensure speed and accuracy.
       - The User Opens the App: This triggers the system to check Redis.
       - The Fast Lane: If a list was generated in the last 5 minutes, it is served instantly from the cache.
       - The Heavy Lifting: If the cache is empty, the system pulls data from the Database, runs it through the AI (LLM) for filtering, calculates the final Heat Scores, and updates the cache for the next user.
       ![Demo](front-end/src/assets/demo.png)
4. 
