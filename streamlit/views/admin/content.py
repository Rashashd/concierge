"""Admin — Content management page."""
from __future__ import annotations

from typing import Any

import streamlit as st

from utils import _delete, _format_dt, _get_json, _post_json, _put_json

_CONTENT_TYPES = ["faq", "page", "blog"]
_TYPE_LABELS = {"faq": "FAQ", "page": "Page", "blog": "Blog"}


def render(backend_url: str, token: str) -> None:
    st.title("Content")
    st.caption("Add FAQs, pages, and blog posts that the AI assistant can reference.")
    st.write("")

    if st.session_state.pop("content_created", False):
        st.success("Content item added successfully.")

    with st.expander(
        "Add new content item",
        expanded=st.session_state.get("expand_add_content", False),
    ):
        with st.form("add_content_form"):
            add_title = st.text_input("Title")
            add_type = st.selectbox(
                "Type", _CONTENT_TYPES,
                format_func=lambda x: _TYPE_LABELS.get(x, x.title()),
            )
            add_body = st.text_area("Body", height=200)
            add_submitted = st.form_submit_button(
                "Add content", type="primary", use_container_width=True
            )
        if add_submitted:
            if not add_title or not add_body:
                st.warning("Title and body are required.")
            else:
                result = _post_json(
                    f"{backend_url}/content",
                    {"title": add_title, "body": add_body, "content_type": add_type},
                    token,
                )
                if result:
                    st.session_state["content_created"] = True
                    st.session_state["expand_add_content"] = False
                    st.session_state.pop("content_data", None)
                    st.rerun()

    st.write("")

    _, limit_col, refresh_col = st.columns([4, 1, 1])
    with limit_col:
        page_size = st.selectbox(
            "Show", [10, 25, 50], index=0, label_visibility="collapsed", key="content_page_size"
        )
    with refresh_col:
        if st.button("Refresh", use_container_width=True, key="refresh_content"):
            st.session_state.pop("content_data", None)

    if "content_data" not in st.session_state:
        with st.spinner("Loading content..."):
            data = _get_json(f"{backend_url}/content", token)
            st.session_state["content_data"] = data or []

    content_items: list[dict[str, Any]] = st.session_state.get("content_data", [])

    if not content_items:
        st.info("No content yet. Add your first item above.")
        return

    total_items = len(content_items)
    if total_items > page_size:
        st.caption(f"Showing {page_size} of {total_items} items.")

    for item in content_items[:page_size]:
        cid = item["id"]
        with st.container(border=True):
            top, actions = st.columns([5, 2])
            with top:
                st.markdown(f"**{item['title']}**")
                type_label = _TYPE_LABELS.get(item["content_type"], item["content_type"].title())
                st.caption(f"{type_label}   ·   updated {_format_dt(item['updated_at'])}")
            with actions:
                btn_edit, btn_del = st.columns(2)
                with btn_edit:
                    if st.button("Edit", key=f"edit_open_{cid}"):
                        cur = st.session_state.get(f"show_edit_{cid}", False)
                        st.session_state[f"show_edit_{cid}"] = not cur
                with btn_del:
                    if st.button("Delete", key=f"del_open_{cid}"):
                        cur = st.session_state.get(f"show_del_{cid}", False)
                        st.session_state[f"show_del_{cid}"] = not cur

            # Edit panel
            if st.session_state.get(f"show_edit_{cid}"):
                with st.form(f"edit_form_{cid}"):
                    edit_title = st.text_input("Title", value=item["title"])
                    edit_type = st.selectbox(
                        "Type",
                        _CONTENT_TYPES,
                        index=_CONTENT_TYPES.index(item["content_type"])
                        if item["content_type"] in _CONTENT_TYPES
                        else 0,
                        format_func=lambda x: _TYPE_LABELS.get(x, x.title()),
                    )
                    edit_body = st.text_area("Body", value=item["body"], height=200)
                    save_submitted = st.form_submit_button(
                        "Save changes", type="primary", use_container_width=True
                    )
                if save_submitted:
                    updated = _put_json(
                        f"{backend_url}/content/{cid}",
                        {"title": edit_title, "body": edit_body, "content_type": edit_type},
                        token,
                    )
                    if updated:
                        st.session_state.pop(f"show_edit_{cid}", None)
                        st.session_state.pop("content_data", None)
                        st.rerun()

            # Delete confirmation
            if st.session_state.get(f"show_del_{cid}"):
                with st.container(border=True):
                    st.warning(f"Delete **{item['title']}**? This cannot be undone.")
                    c_ok, c_cancel = st.columns(2)
                    with c_ok:
                        if st.button("Yes, delete", key=f"do_del_{cid}", type="primary"):
                            if _delete(f"{backend_url}/content/{cid}", token):
                                st.session_state.pop(f"show_del_{cid}", None)
                                st.session_state.pop("content_data", None)
                                st.rerun()
                    with c_cancel:
                        if st.button("Cancel", key=f"cancel_del_{cid}"):
                            st.session_state.pop(f"show_del_{cid}", None)
                            st.rerun()
