# SlowMotion-Shining-Mask
A slow motion player frame by frame for the Shining Mask. I made it for my bad apple video.


# Preface 

To do this, I used theese links:

https://www.reddit.com/r/ReverseEngineering/comments/lr9xxr/help_me_figure_out_how_to_reverse_engineer_the/?tl=ru
https://github.com/shawnrancatore/shining-mask
https://github.com/BrickCraftDream/Shining-Mask-stuff
https://github.com/BishopFox/shining-mask

I read carefully, and I chose what might be needed in the project. So what I tried to do:

1. Find mask's address
2. Make a lot of tests to choose, what we **ACTUALLY** need
3. Make a final script
4. Adjust timings
5. Start recording

And in the end, that's exactly what I did. 

It took me around 40-50 hours to make this. And finally it works! I'm really happy, that I am able to make it.

# Disclamer

I was the first one to make this. I think that someone can do better, but this is really great thing - I thought that it is not possible to record a video on this even in slow motion. Don't judge strictly.

# How to use

Technically, you need only two scripts: [findMask.py](https://github.com/Kolya080808/SlowMotion-Shining-Mask/blob/main/findMask.py) and [final.py](https://github.com/Kolya080808/SlowMotion-Shining-Mask/blob/main/final.py). The first one helps you to find the mask address, second to start.

Also I used ffmpeg to extract from video frames:

```bash
mkdir -p frames-video
ffmpeg -i "$VIDEO_FILE" -vf fps=30 frames-video/out%05d.jpg
```

Then, you need to start the first script and copy mask address.

And after that, you paste the mask address to the final script, adjust some settings (such as WORKING_SLOT_ID - where images will be shown - I have the first 6 occupied, so the 7th is working; DELAY - the more time you give, the bigger quality of convertion, but the slower time; DISPLAY_CYCLE - every x (for me x=7) secs the image will be shown - that's made for the timelapse timings; DISPLAY_CORRECTION - I have some tolerance on timelapse, so I made this variable to fix it - for every timelapse camera it's different) and it's ready to start! Turn on your mask and start the script.

# Videos

- [YouTube](https://youtu.be/Xaw0n_ccmGc)
- [Telegram Channel](https://bezhopasnik.t.me) ([this post and the post after it](https://t.me/bezhopasnik/2163))
- [Reddit](https://www.reddit.com/r/badapple/comments/1qnnvxr/bad_apple_but_played_on_shining_mask/) (not working, got shadowban)
