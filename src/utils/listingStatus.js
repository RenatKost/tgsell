// Channel listing status labels (cabinet, admin). Keep in sync with ChannelStatus.
export const LISTING_STATUS = {
	pending: { text: 'На модерації', tone: 'yellow' },
	needs_clarification: { text: 'Очікує уточнення', tone: 'orange' },
	approved: { text: 'Опубліковано', tone: 'green' },
	rejected: { text: 'Відхилено', tone: 'red' },
	sold: { text: 'Продано', tone: 'gray' },
	removed: { text: 'Знято з біржі', tone: 'gray' },
};
