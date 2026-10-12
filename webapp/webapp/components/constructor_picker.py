"""Small native lists with browser-local search, independent of chart requests."""

import reflex as rx

_PICKER_JS = """
const ConstructorPicker = memo(function ConstructorPicker({options, selected, multiple, onPick}) {
    const [query, setQuery] = useState('');
    const filtered = useMemo(() => {
        const needle = query.trim().toLowerCase();
        return options.filter(item => (item.label || item.name).toLowerCase().includes(needle));
    }, [options, query]);
    const h = React.createElement;
    const groups = multiple ? ['TAKEOFF', 'CRUISE'] : [''];
    return h('div', {style: {width: '100%', minWidth: 0}},
        h('input', {
            type: 'search', value: query,
            placeholder: multiple ? 'Parameter name' : 'Engine or aircraft',
            'aria-label': multiple ? 'Parameter name' : 'Engine or aircraft',
            onChange: event => setQuery(event.target.value),
            style: {boxSizing: 'border-box', width: '100%', height: 28,
                border: '1px solid var(--gray-7)', borderRadius: 4, padding: '0 6px',
                background: 'var(--color-surface)', color: 'var(--gray-12)', font: 'inherit', fontSize: 12}
        }),
        h('div', {style: {maxHeight: multiple ? 260 : 420, overflowY: 'auto',
            overscrollBehavior: 'contain', marginTop: 6}},
            groups.map(phase => h('div', {key: phase},
                multiple && h('div', {style: {fontSize: 12, color: 'var(--gray-10)', margin: '4px 0'}},
                    phase === 'TAKEOFF' ? 'Takeoff' : 'Cruise'),
                filtered.filter(item => !multiple || item.phase === phase).map(item => {
                    const id = item.id || item.key;
                    const checked = selected.includes(id);
                    return multiple
                        ? h('label', {key: id, style: {display: 'flex', alignItems: 'center',
                            gap: 6, minHeight: 22, fontSize: 12, cursor: 'pointer'}},
                            h('input', {type: 'checkbox', checked,
                                onChange: event => onPick(id, event.target.checked),
                                style: {margin: 0, accentColor: 'var(--accent-9)'}}), item.name)
                        : h('button', {key: id, type: 'button', 'aria-pressed': checked,
                            onClick: () => onPick(id, true),
                            style: {display: 'block', width: '100%', textAlign: 'left',
                                border: 0, borderRadius: 4, padding: '4px 6px', cursor: 'pointer',
                                font: 'inherit', fontSize: 12, color: 'var(--gray-12)',
                                background: checked ? 'var(--accent-4)' : 'transparent'}}, item.label);
                })
            )),
            filtered.length === 0 && h('div', {style: {fontSize: 12, padding: 6}}, 'No matches')
        )
    );
});
"""


class ConstructorPicker(rx.Component):
    tag = "ConstructorPicker"
    options: rx.Var[list[dict[str, str]]]
    selected: rx.Var[list[str]]
    multiple: rx.Var[bool]
    on_pick: rx.EventHandler[lambda key, checked: [key, checked]]

    def add_imports(self):
        return {
            "react": [
                "useState",
                "useMemo",
                "memo",
                rx.ImportVar(tag="React", is_default=True),
            ]
        }

    def add_custom_code(self):
        return [_PICKER_JS]
