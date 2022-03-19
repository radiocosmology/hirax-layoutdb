import { 
    Paper, 
    Button, 
    Select, 
    MenuItem } 
from '@mui/material';

import { ArrowForward, ArrowBack } from '@mui/icons-material';

function ElementRangePanel(
        { 
            min, 
            updateMin, 
            range, 
            updateRange, 
            count, 
            rightColumn,
            width,
        }
    ) {

    // function to call when the component range is changed. is changed.
    const handleRangeChange = (event) => {
        updateRange(event.target.value);
    }

    const changeMin = (min, updateMin, range, count, increment) => {
        /*
        Increment the range minimum of components to view.
        */
    
        let newMin = min;
    
        if (increment) {
            if (newMin + range < count) {
                newMin += range;
            }
        }
        else {
            if (newMin < range) {
                newMin = 0;
            }
            else {
                newMin -= range;
            }
        }
    
        updateMin(newMin);
    }

    let max = min + range;
    if (max >= count) {
        max = count;
    }

    let numDisplayText = `Viewing ${min+1}-${max} out of ${count}`
    if (count === 0) {
        numDisplayText = "No objects found";
    }

    let paperWidth = (width) ? width : '600px';

    // return the range panel.
    return (
        <Paper
            style={{
                marginTop: '16px',
                paddingTop: '8px',
                paddingBottom: '8px',
                flexGrow: 1,
                marginBottom: '8px',
                textAlign: 'center',
                display: 'grid',
                justifyContent: 'space-between',
                rowGap: '8px',
                width: paperWidth,
                maxWidth: '100%',
                margin: 'auto',
            }}
        >
            <div
                style={{
                    paddingTop: '8px',
                    gridRow: 1,
                    gridColumn: 1,
                    margin: 'auto'
                }}>
                {numDisplayText}
            </div>
            <div
                style={{
                    gridRow: 2,
                    gridColumn: '1 / 2',
                    margin: 'auto', 
                }}>
                <Button 
                    color="primary" 
                    style={{
                        marginRight: '8px',
                        marginLeft: '8px',
                        padding: '16px',
                    }}
                    onClick={() => {
                        changeMin(min, updateMin, range, count, false)
                    }}
                    disabled={min <= 0}
                >
                    <ArrowBack />
                </Button>

                Show 
                <Select
                    labelId="range-select-label"
                    id="range-select"
                    value={range}
                    onChange={handleRangeChange}
                    style={{
                        marginRight: '8px',
                        marginLeft: '8px',
                    }}
                    displayEmpty 
                >
                    <MenuItem value={10}>10</MenuItem>
                    <MenuItem value={25}>25</MenuItem>
                    <MenuItem value={50}>50</MenuItem>
                    <MenuItem value={100}>100</MenuItem>
                </Select>
                at a time

                <Button 
                    color="primary" 
                    style={{
                        marginRight: '8px',
                        marginLeft: '8px',
                        padding: '16px',
                    }}
                    onClick={() => {
                        changeMin(min, updateMin, range, count, true)
                    }}
                    disabled={max >= count}
                >
                    <ArrowForward />
                </Button>
            </div>

            <div
                style={{
                    marginLeft: '16px',
                    marginRight: '16px',
                    gridRow: '1 / 3',
                    gridColumn: 2,
                    marginTop: 'auto',
                    marginBottom: 'auto'
                }}>
                {rightColumn}
            </div>
        </Paper>
    )
}

export default ElementRangePanel;