import logging
import os
import re
from datetime import datetime
from typing import Optional

from fastmcp import FastMCP
from redditwarp.ASYNC import Client
from redditwarp.models.comment_tree_ASYNC import CommentTreeNode
from redditwarp.models.submission_ASYNC import GalleryPost, LinkPost, TextPost

mcp = FastMCP("Reddit MCP")

REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_REFRESH_TOKEN = os.getenv("REDDIT_REFRESH_TOKEN")

CREDS = [x for x in [REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_REFRESH_TOKEN] if x]

client = Client(*CREDS)
logging.getLogger().setLevel(logging.DEBUG)


@mcp.tool()
async def fetch_reddit_post_from_url(reddit_url: str):
    """
    Fetch general data from a Reddit submission URL.

    Args:
        reddit_url: The full URL of the Reddit post.

    Returns:
        Human readable string containing post information.
    """
    try:
        # Extract post_id from URL
        # Example URL: https://www.reddit.com/r/learnpython/comments/12345ab/my_first_python_project/
        # Example URL: https://reddit.com/r/learnpython/comments/12345ab/
        match = re.search(r"/comments/([^/]+)", reddit_url)
        if not match:
            return "Invalid Reddit post URL. Could not extract post ID."
        post_id = match.group(1)

        submission = await client.p.submission.fetch(post_id)

        logging.info(f"Fetched submission: {submission}")

        main_content_parts = [
            f"Title: {submission.title}",
            f"Score: {submission.score}",
            f"Author: {submission.author_display_name or '[deleted]'}",
            f"Subreddit: {submission.subreddit.name}",
            f"Type: {_get_post_type(submission)}",
            f"Content: {_get_content(submission)}",
            f"Link: https://reddit.com{submission.permalink}",
            f"Number of Comments: {submission.comment_count}",
        ]

        # Fetch and format all comments
        comment_limit = None  # Fetch all top-level comments
        comment_depth = None  # Fetch all replies to any depth
        comment_forest = await client.p.comment_tree.fetch(
            post_id, sort="top", limit=comment_limit, depth=comment_depth
        )

        if comment_forest.children:
            comments_header = "Comments:"
            formatted_top_comments = []
            for top_level_comment_node in comment_forest.children:
                formatted_top_comments.append(
                    _format_comment_tree(top_level_comment_node, depth=0)
                )

            if formatted_top_comments:
                # Join the header and individual formatted comment trees with a single newline.
                # Each _format_comment_tree output is already a multi-line block.
                comments_section_str = (
                    comments_header + "\n" + "\n".join(formatted_top_comments)
                )
                main_content_parts.append(comments_section_str)

        return main_content_parts

    except Exception as e:
        logging.error(
            f"An error occurred while fetching post from URL {reddit_url}: {str(e)}"
        )
        return f"An error occurred: {str(e)}"


@mcp.tool()
async def fetch_reddit_hot_threads(subreddit: str, limit: int = 10) -> str:
    """
    Fetch hot threads from a subreddit

    Args:
        subreddit: Name of the subreddit
        limit: Number of posts to fetch (default: 10)

    Returns:
        Human readable string containing list of post information
    """
    try:
        posts = []
        async for submission in client.p.subreddit.pull.hot(subreddit, limit):
            post_info = (
                f"Title: {submission.title}\n"
                f"Score: {submission.score}\n"
                f"Comments: {submission.comment_count}\n"
                f"Author: {submission.author_display_name or '[deleted]'}\n"
                f"Type: {_get_post_type(submission)}\n"
                f"Content: {_get_content(submission)}\n"
                f"Link: https://reddit.com{submission.permalink}\n"
                f"---"
            )
            posts.append(post_info)

        return "\n\n".join(posts)

    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return f"An error occurred: {str(e)}"


def _format_date(timestamp: float) -> str:
    """Helper method to format UTC timestamp to a readable date string."""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S UTC")


def _format_comment_tree(comment_node: CommentTreeNode, depth: int = 0) -> str:
    """Helper method to recursively format comment tree with proper indentation"""
    comment = comment_node.value
    result = ""

    author_name = comment.author_display_name or "[deleted]"
    created_date = _format_date(comment.created_ut)

    indent = "    " * depth

    result += f"{indent}{created_date} [{author_name}] Score: {comment.score}\n"
    result += f"{indent}{comment.body}\n"

    # Sort replies by creation time, newest first
    sorted_replies = sorted(
        comment_node.children,
        key=lambda reply_node: reply_node.value.created_ut,
        reverse=True,
    )

    for child_node in sorted_replies:
        result += f"{indent}> " + _format_comment_tree(child_node, depth + 1)

    return result


@mcp.tool()
async def fetch_reddit_post_content(
    post_id: str, comment_limit: int = 20, comment_depth: int = 3
) -> str:
    """
    Fetch detailed content of a specific post

    Args:
        post_id: Reddit post ID
        comment_limit: Number of top level comments to fetch
        comment_depth: Maximum depth of comment tree to traverse

    Returns:
        Human readable string containing post content and comments tree
    """
    try:
        submission = await client.p.submission.fetch(post_id)

        content = (
            f"Title: {submission.title}\n"
            f"Score: {submission.score}\n"
            f"Author: {submission.author_display_name or '[deleted]'}\n"
            f"Type: {_get_post_type(submission)}\n"
            f"Content: {_get_content(submission)}\n"
        )

        comments = await client.p.comment_tree.fetch(
            post_id, sort="top", limit=comment_limit, depth=comment_depth
        )
        if comments.children:
            content += "\nComments:\n"
            for comment in comments.children:
                content += "\n" + _format_comment_tree(comment)
        else:
            content += "\nNo comments found."

        return content

    except Exception as e:
        return f"An error occurred: {str(e)}"


def _get_post_type(submission) -> str:
    """Helper method to determine post type"""
    if isinstance(submission, LinkPost):
        return "link"
    elif isinstance(submission, TextPost):
        return "text"
    elif isinstance(submission, GalleryPost):
        return "gallery"
    return "unknown"


def _get_content(submission) -> Optional[str]:
    """Helper method to extract post content based on type"""
    if isinstance(submission, LinkPost):
        return submission.permalink
    elif isinstance(submission, TextPost):
        return submission.body
    elif isinstance(submission, GalleryPost):
        return str(submission.gallery_link)
    return None
