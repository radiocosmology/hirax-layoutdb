import React, { useState, useEffect } from 'react';

import ElementList from './ElementList.js';
import ElementRangePanel from './ElementRangePanel.js';
import PropertyTypeFilter from './PropertyTypeFilter.js';
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress';
import TextField from '@mui/material/TextField';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Box from '@mui/material/Box';
import InputLabel from '@mui/material/InputLabel';
import MenuItem from '@mui/material/MenuItem';
import FormControl from '@mui/material/FormControl';
import Select from '@mui/material/Select';
import { useTheme } from '@mui/material/styles';
import OutlinedInput from '@mui/material/OutlinedInput';
import Chip from '@mui/material/Chip';
import axios from 'axios'
import FormHelperText from '@mui/material/FormHelperText';

/**
 * A MUI component that renders a list of property types.
 */
export default function PropertyTypeList() {

    // the list of property types in objects representation
    const [elements, setElements] = useState([]);

    // the first index to show
    const [min, setMin] = useState(0);

    // how many elements there are
    const [count, setCount] = useState(0);

    // the number of elements to show
    const [range, setRange] = useState(100);

    // whether the elements are loaded or not
    const [loaded, setLoaded] = useState(false);

    // property to order the component types by
    // must be in the set {'name, units, allowed_regex, n_values'}
    const [orderBy, setOrderBy] = useState('name');

    // how to order the elements
    // 'asc' or 'desc'
    const [orderDirection,
        setOrderDirection] = useState('asc');

    const [componentTypes, setComponentTypes] = useState([]);

    /* filters stored as 
        [
            {
            name: <str>,
            types: <str>,
            },
            ...
        ]
    */
    const [filters, setFilters] = useState([]);

    /**
     * add an empty filter to filters
     */ 
    const addFilter = () => {
        setFilters([...filters, {
            name: "",
            type: "",
        }])
    }

   /**
     * Remove a filter at some index.
     * @param {int} index - index of the new filter to be removed.
     * 0 <= index < filters.length
     */
    const removeFilter = (index) => {
        if (index >= 0 && index < filters.length) {
            let newFilters = filters.filter((element, i) => index !== i);
            setFilters(newFilters);
        }
    }

    /**
     * Change the filter at index :index: to :newFilter:.
     * @param {int} index - index of the new filter to be changed
     * 0 <= index < filters.length
     **/
    const changeFilter = (index, newFilter) => {
        if (index >= 0 && index < filters.length) {
            // make a shallow copy of the filters
            let filters_copy = [...filters];

            // set the element at index to the new filter
            filters_copy[index] = newFilter;

            // update the state array
            setFilters(filters_copy);
        }
    }

   /**
    * To send the filters to the URL, create a string that contains all the
    * filter information.
    * 
    * The string is of the format
    * "<name>,<ctype_name>;...;<name>,<ctype_name>"
    * @returns Return a string containing all of the filter information
    */
    const createFilterString = () => {

        let strSoFar = "";

        if (filters.length > 0) {

            // create the string 
            for (let f of filters) {
                strSoFar += `${f.name},${f.type};`;
            }

            // remove the last semicolon.
            strSoFar = strSoFar.substring(0, strSoFar.length - 1);
        }

        return strSoFar;
    }

    const [reloadBool, setReloadBool] = useState(false);
    function toggleReload() {
        setReloadBool(!reloadBool);
    }
   /**
    * The function that updates the list of property types when the site is 
    * loaded or a change of the property types is requested 
    * (upon state change).
    */
    useEffect(() => {
        async function fetchData() {
            setLoaded(false);

            // create the URL query string
            let input = '/api/property_type_list';
            input += `?range=${min};${min + range}`;
            input += `&orderBy=${orderBy}`;
            input += `&orderDirection=${orderDirection}`;
            if (filters.length > 0) {
                input += `&filters=${createFilterString()}`;
            }

            // query the URL with flask, and set the input.
            fetch(input).then(
                res => res.json()
            ).then(data => {
                setElements(data.result);
                setLoaded(true);
            });
        }
        fetchData();
    }, [
        min,
        range,
        orderBy,
        orderDirection,
        filters,
        reloadBool
    ]);

    /**
     * Change the property type count when filters are updated.
     */
    useEffect(() => {
        let input = `/api/property_type_count`;
        if (filters.length > 0) {
            input += `?filters=${createFilterString()}`;
        }
        fetch(input).then(
            res => res.json()
        ).then(data => {
            setCount(data.result);
            setMin(0);
        });
    }, [
        filters,
        reloadBool
    ]);

    /**
     * Load all of the component types (so they can be used for the filter)
     * 
     * TODO: THIS IS GARBAGE, WILL BE REALLY REALLY SLOW WHEN YOU HAVE A LOT
     * OF COMPONENT TYPES. INSTEAD, MAKE A COMPONENT TYPE AUTOCOMPLETE AND
     * THEN USE THEM IN THE FILTERS INSTEAD OF THIS PILE OF TRASH.
     */
    useEffect(() => {

        let input = '/api/component_type_list'
        input += `?range=0;-1`
        input += `&orderBy=name`
        input += `&orderDirection=asc`
        input += `&nameSubstring=`
        fetch(input).then(
            res => res.json()
        ).then(data => {
            setComponentTypes(data.result);
        });
    }, []);

    // the header cells of the table with their ids, labels, and whether you
    // can order by them.
    const tableHeadCells = [
        {
            id: 'name', 
            label: 'Property Type',
            allowOrdering: true,
        },
        {
            id: 'allowed_type', 
            label: 'Allowed Types',
            allowOrdering: true,
        },
        {
            id: 'units', 
            label: 'Units',
            allowOrdering: false,
        },
        {
            id: 'allowed_regex', 
            label: 'Allowed Regex',
            allowOrdering: false,
        },
        {
            id: 'n_values', 
            label: '# of Values',
            allowOrdering: false,
        },
        {
            id: 'comments', 
            label: 'Comments',
            allowOrdering: false,
        }
    ];

    /**
     * the rows of the table. We are only putting:
     * - the name,
     * - a list of the property type's allowed types,
     * - the units,
     * - the allowed regex for the property type,
     * - the number of values a property must have, and
     * - the comments associated with the property type.
     */
    let tableRowContent = elements.map((e) => [
        e.name,
        e.allowed_types.sort().join(', '),
        e.units,
        e.allowed_regex,
        e.n_values,
        e.comments
    ]);

const ITEM_HEIGHT = 48;
const ITEM_PADDING_TOP = 8;
const MenuProps = {
  PaperProps: {
    style: {
      maxHeight: ITEM_HEIGHT * 4.5 + ITEM_PADDING_TOP,
      width: 300,
    },
  },
};

function getStyles(name, componentTypeName, theme) {
  return {
    fontWeight:
      componentTypeName.indexOf(name) === -1
        ? theme.typography.fontWeightRegular
        : theme.typography.fontWeightMedium,
  };
}



  const PropertyTypeAddButton = ({componentTypes}) => {

  const [open, setOpen] = useState(false);
  const [isError,setIsError] = useState(false)
  const [componentTypeName, setComponentTypeName] = useState([]);
  const [property,setProperty] = useState({
    name: '',
    units:'',
    allowed_regex:'',
    values:0,
    comment:''
  })
  const [loading, setLoading] = useState(false);
  const theme = useTheme();

  /*
  Keeps a record of multiple state values.
   */
  const handleChange2 = (e) =>{
    const name = e.target.name
    const value = e.target.value
    setProperty({...property,[name]:value})
  }

  /*This handleChange function is specifically for storing
  multiple values of the allowed component types.
  */
  const handleChange = (event) => {
    const {
      target: { value },
    } = event;
    setComponentTypeName(
      // On autofill we get a stringified value.
      typeof value === 'string' ? value.split(',') : value,
    );
  };

  const handleClickOpen = () => {
    setOpen(true);
  };

  /*
  This function sets the variables back to empty string once 
  the form is closed or the user clicks on the cancel button
  on the pop up form.
  */
  const handleClose = () => {
    setOpen(false);
    setIsError(false)
    setLoading(false)
    setComponentTypeName([])
    setProperty({
    name: '',
    units:'',
    allowed_regex:'',
    values:0,
    comment:''
  })
  };

  const handleSubmit = (e) => {
    e.preventDefault() // To preserve the state once the form is submitted.

    /*
    These conditions don't allow the user to submit the form if the property type name, 
    component type, units, allowed regex or number of values fields in the form
    are left empty.
     */
    if(property.name && componentTypeName && property.units &&property.allowed_regex && property.values !=0){ 
    let input = `/api/set_property_type`;
    input += `?name=${property.name}`;
    input += `&type=${componentTypeName.join(';')}`;
    input += `&units=${property.units}`;
    input += `&allowed_reg=${property.allowed_regex}`;
    input += `&values=${property.values}`;
    input += `&comments=${property.comment}`;
    axios.post(input).then((response)=>{
      
          toggleReload() //To reload the page once the form has been submitted.
    })
    } else {
      setIsError(true) 
    }
  }

  return (
    <>
        <Button variant="contained" onClick={handleClickOpen}>Add Property Type</Button>
      <Dialog open={open} onClose={handleClose}>
        <DialogTitle>Add Property Type</DialogTitle>
        <DialogContent>
    <div style={{
        marginTop:'10px',
    }}>
          <TextField
            error={isError}
            helperText = {isError ? 'Cannot be empty' : ''}
            autoFocus
            margin="dense"
            id="name"
            label="Property Type"
            type='text'
            fullWidth
            variant="outlined"
            name = 'name'
            value={property.name}
            onChange={handleChange2}
            />
    </div>

    <div style={{
        marginTop:'15px',
        marginBottom:'15px',
    }}>   
            <FormControl sx={{width: 300}} error = {isError}>
        <InputLabel id="Allowed Type">Allowed Type</InputLabel>
        <Select
          labelId="multiple-Allowed-Type-label"
          id="multiple-Allowed-Type"
          multiple
          value={componentTypeName}
          onChange={handleChange}
          input={<OutlinedInput id="select-multiple-Allowed-Type" label="Allowed-Type" />}
          renderValue={(selected) => (
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
              {selected.map((value) => (
                <Chip key={value} label={value} />
              ))}
            </Box>
          )}
          MenuProps={MenuProps}
        >
          {componentTypes.map((component) => {

            return (
              <MenuItem
              key={component.name}
              value={component.name}
              style={getStyles(component.name, componentTypeName, theme)}
              >
              {component.name}
            </MenuItem>
          )}
          )}
        </Select>
        {
        isError ? 
        <FormHelperText>Cannot be empty</FormHelperText> 
        : 
        ''
        }
      </FormControl>
    </div>
    <div style={{
        marginTop:'10px',
    }}>
          <TextField
            error={isError}
            helperText = {isError ? 'Cannot be empty' : ''}
            autoFocus
            margin="dense"
            id="units"
            label="Units"
            type='text'
            fullWidth
            variant="outlined"
            name = 'units'
            value={property.units}
            onChange={handleChange2}
            />
    </div>
    <div style={{
        marginTop:'10px',
        marginBottom:'10px'
    }}>
          <TextField
            error={isError}
            helperText = {isError ? 'Cannot be empty' : ''}
            autoFocus
            margin="dense"
            id="Allowed Regex"
            label="Allowed Regex"
            type='text'
            fullWidth
            variant="outlined"
            name = 'allowed_regex'
            value={property.allowed_regex}
            onChange={handleChange2}
            />
    </div>
    <div style={{
        marginTop:'20px',
        marginBottom:'10px'
    }}>
          <TextField
          error={isError}
          helperText = {isError ? 'Cannot be empty' : ''}
          id="outlined-number"
          label="Number of Values"
          type="number"
          name = 'values'
          value={property.values}
          onChange={handleChange2}
          InputLabelProps={{
            shrink: true,
          }}
        />
    </div>

    <div style={{
        marginTop:'10px',
        marginBottom:'10px'
    }}>
          <TextField
            margin="dense"
            id="comment"
            label="Comment"
            multiline
            maxRows={4}
            type="text"
            fullWidth
            variant="outlined"
            name = 'comment'
            value={property.comment}
            onChange={handleChange2}
            />
    </div>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClose}>Cancel</Button>
          <Button onClick={handleSubmit}>
              {loading ? <CircularProgress
                            size={24}
                            sx={{
                                color: 'blue',
                            }}
                        /> : "Submit"}
              </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

    return (
        <>
            <ElementRangePanel
                width="800px"
                min={min}
                updateMin={(n) => { setMin(n) }}
                range={range}
                updateRange={(n) => { setRange(n) }}
                count={count}
                rightColumn={
                    (
                        <Button
                            variant="contained"
                            color="primary"
                            onClick={addFilter}
                        >
                            Add Filter
                        </Button>
                    )
                }
                rightColumn2 = {
                    <PropertyTypeAddButton componentTypes={componentTypes}/>
                }
            />

            {
                filters.map(
                    (filter, index) => (
                        <PropertyTypeFilter
                            key={index}
                            width="700px"
                            addFilter={() => { }}
                            removeFilter={removeFilter}
                            changeFilter={changeFilter}
                            filter={filter}
                            index={index}
                            types={componentTypes}
                        />
                    )
                )
            }

            <ElementList
                width="800px"
                tableRowContent={tableRowContent}
                loaded={loaded}
                orderBy={orderBy}
                direction={orderDirection}
                setOrderBy={setOrderBy}
                setOrderDirection={setOrderDirection}
                tableHeadCells={tableHeadCells}
            />
        </>

    )
}