import cmor
import xarray as xr
import pathlib


class O4MConverter:
    def __init__(self, *, gas, input_json, cmor_tabpath, cmor_tabname, logfile):
        # loads CMOR tables
        self.input_json = input_json
        self.cmor_tables_path = cmor_tabpath
        self.cmor_tabname = cmor_tabname
        self.gas = gas
        self.logfile = logfile

        # define variable attributes
        if gas == 'co2':
            self.varname = f'x{gas.lower()}'
            self.gas_long_name = 'carbon dioxide'
            self.gas_standard_name = 'carbon_dioxide'
            self.units = '1'
            self.standard_name = f'dry_atmosphere_mole_fraction_of_{self.gas_standard_name}'
            self.long_name = f'column-averaged dry-air mole fraction of atmospheric {self.gas_long_name}'
            self.data_type = 'f'
            # data_types: ‘d’ (double), ‘f’ (float), ‘l’ (long) or ‘i’ (int)

        elif gas == 'ch4':
            self.varname = f'x{gas.lower()}'
            self.gas_long_name = 'methane'
            self.gas_standard_name = 'methane'
            self.units = '1'
            self.standard_name = f'dry_atmosphere_mole_fraction_of_{self.gas_standard_name}'
            self.long_name = f'column-averaged dry-air mole fraction of atmospheric {self.gas_long_name}'
            self.data_type = 'f'

        cmor.setup(inpath=self.cmor_tables_path,
                   set_verbosity=cmor.CMOR_NORMAL,
                   netcdf_file_action=cmor.CMOR_APPEND_4,
                   logfile=self.logfile)
        cmor.dataset_json(self.input_json)
        cmor.load_table(self.cmor_tables_path + self.cmor_tabname)


    def create_axes (self, ds):
        """
        """
        lat = ds.lat.values
        lat_bnds = ds.lat_bnds.values
        lon = ds.lon.values
        lon_bnds = ds.lon_bnds.values
        time = ds.time.values
        time_bnds = ds.time_bnds.values

        cmorLat = cmor.axis(table_entry="latitude",
                            coord_vals=lat[:],
                            cell_bounds=lat_bnds,
                            units="degrees_north")

        cmorLon = cmor.axis("longitude",
                            coord_vals=lon[:], cell_bounds=lon_bnds, units="degrees_east")

        cmorTime = cmor.axis("time",
                             coord_vals=time[:], cell_bounds=time_bnds,
                             units='days since 1990-01-01')

        return [cmorTime, cmorLat, cmorLon]

    def create_cmor_var (self, vardata, axes, varname, attrs, main_var=False, ancillary_vars=[], aux_uncert_vars=[]):
        """

        Args:

            attrs (dict): 
                - required keys: units, data_type, missing_value
                - optional keys: long_name
            
            main_var (bool): True if writing main O4M var.
            ancillary_vars (list): list of strings with names of ancillary variables
            aux_uncert_vars (list): list of suffixes to characterize uncertainty (from ODS >2.6.1)

        """
        varid = cmor.variable(table_entry=varname,
                                   units=attrs['units'],
                                   axis_ids=axes,
                                   data_type=attrs['data_type'],
                                   missing_value=attrs['missing_value'],
                                   )
        if 'long_name' in attrs:
            cmor.set_variable_attribute(varid, 'long_name', 'c', self.long_name)
        
        if main_var:
            cmor.set_variable_attribute(varid, 'ancillary_variables', 'c', ' '.join(ancillary_vars))

            cmor.set_variable_attribute(varid, 'aux_uncertainty_id', 'c', ' '.join(aux_uncert_vars))

        cmor.set_deflate(varid, 1, 1, 1)
        cmor.write(varid, vardata)
        file_name = cmor.close(varid, file_name=True)

        return file_name


    def create_ancillary_var (self, varname, path_out, ds0, main_var_path, main_var_name):
        """
        
        It keeps the variable name from the source dataset.
        
        Args:
            varname: ancillary variable name
            path_out
            ds0: source dataset to copy variable from
        """
        with xr.open_dataset(main_var_path, decode_times=False, chunks=None) as ds:
            ds.load()
        pathlib.Path('/'.join(path_out.split('/')[:-1])).mkdir(exist_ok=True, parents=True)

        ds_anc = ds.copy(deep=True).drop_vars(main_var_name)
        # add ancillary variables from source dataset
        ds_anc[varname] = (ds0[varname].dims, ds0[varname].values)
        ds_anc[varname].attrs = ds0[varname].attrs

        if 'fill_value' in ds_anc[varname].attrs:
            ds_anc[varname].attrs['_FillValue'] = ds0[varname].attrs['fill_value']
            ds_anc[varname].attrs.pop("fill_value", None)

        encoding = {
            'lat': {'zlib': False, '_FillValue': None},
            'lon': {'zlib': False, '_FillValue': None},
            'time': {'zlib': False, '_FillValue': None},
            'lat_bnds': {'zlib': False, '_FillValue': None},
            'lon_bnds': {'zlib': False, '_FillValue': None},
            'time_bnds': {'zlib': False, '_FillValue': None},
            }

        if 'pre' in ds_anc.coords:
            ds_anc.coords['pre'] = (ds_anc['pre'].dims, ds_anc['pre'].values)
            pre_attrs = {'long_name': 'Pressure normalized by surface pressure',
                    'units': '1',
                    'axis': 'Z',
                    'comment': 'Pressure (normalized by surface pressure) centre of vertical layer',
                    'bounds': 'pre_bnds'}
            ds_anc.coords['pre'].attrs = pre_attrs

            ds_anc.pre_bnds.attrs.clear()
            pre_bnds_attrs = {
                'long_name': 'Pressure boundaries normalized by surface pressure',
                'units': '1',
                        }
            for key, val in pre_bnds_attrs.items():
                ds_anc.pre_bnds.attrs[key] = val

            encoding.update({
                'pre': {'zlib': False, '_FillValue': None},
                'pre_bnds': {'zlib': False, '_FillValue': None}
            })

        ds_anc.to_netcdf(path_out, engine='netcdf4',
                    format='NETCDF4', encoding=encoding)

        print(f'Saved {path_out}')


def main(*, gas, cmor_tabpath, cmor_tabname, input_file, input_json, logfile):
    """
    """
    oconv = O4MConverter(gas=gas,
                          input_json=input_json,
                          cmor_tabpath=cmor_tabpath,
                          cmor_tabname=cmor_tabname,
                          logfile=logfile)

    with xr.open_dataset(input_file, decode_times=False, chunks=None) as ds0:
        ds0.load()
        ds0 = ds0.swap_dims({'pressure': 'pre'})

    axes = oconv.create_axes(ds0)

    nobs_source_varname = oconv.varname + '_nobs'
    stderr_source_varname = oconv.varname + '_stderr'
    sd_source_varname = oconv.varname + '_stddev'

    uncert_vars = {
        oconv.varname + 'nobs': {
            'source_varname': nobs_source_varname,
            'attrs': {
                'units': '1',
                'data_type': 'l',
                'missing_value': 0,
                }
        },
        oconv.varname + 'stderr': {
            'source_varname': stderr_source_varname,
            'attrs': {
                'units': '1',
                'data_type': oconv.data_type,
                'missing_value': 1E20,
                }
        },
        oconv.varname + 'sd': {
            'source_varname': sd_source_varname,
            'attrs': {
                'units': '1',
                'data_type': oconv.data_type,
                'missing_value': 1E20,
                }
        }
    }

    uncert_source_varnames = [vals['source_varname'] for vals in uncert_vars.values()]

    ancillary_vars = [
        vari for vari in ds0.data_vars if (
            (vari != oconv.varname) and
            (vari not in uncert_source_varnames) and
            (not vari.endswith('_bnds'))
            )]

    # main xghg variable
    out_filename_main = oconv.create_cmor_var (
                            vardata=ds0[oconv.varname].values,
                            axes=axes,
                            varname=oconv.varname,
                            attrs={'units': oconv.units,
                                    'data_type': oconv.data_type,
                                    'missing_value': 1E20,
                                    'long_name': oconv.long_name
                                    },
                            main_var=True,
                            aux_uncert_vars=list(uncert_vars.keys()),
                            ancillary_vars=ancillary_vars
                            )

    # uncert variables
    for new_varname, vals in uncert_vars.items():
        source_varname = vals['source_varname']

        if source_varname == nobs_source_varname:
            vardata = ds0[source_varname].fillna(0).astype(int).values
        elif (
            (source_varname == sd_source_varname) or
            (source_varname == stderr_source_varname)
            ):
            vardata = ds0[source_varname].fillna(0).values

        oconv.create_cmor_var(
                            vardata=vardata,
                            axes=axes,
                            varname=new_varname,
                            attrs=vals['attrs'],
                            main_var=False,
                            )

    for anci in ancillary_vars:
        filename_anci = out_filename_main.replace(oconv.varname, anci)
        oconv.create_ancillary_var (varname=anci,
                                    path_out=filename_anci,
                                    ds0=ds0,
                                    main_var_path=out_filename_main,
                                    main_var_name=oconv.varname
                                    )
    return


if __name__ == '__main__':
    import os
    ### Info source dataset
    gas = 'co2' # options: co2, ch4
    version = '4.6'  # dataset version
    date_start = '200301' # start date of dataset
    date_end = '202312' # end date of dataset

    # path to source file
    vv = ''.join(version.split('.'))
    input_file = f'O4M/source_data/x{gas}_c3s_l3_v{vv}_{date_start}_{date_end}.nc'

    cwd = os.getcwd()

    input_json = cwd + f'/inputs/IUP-UB/C3S-XGHG-v4-6/C3S_X{gas.upper()}_ECV_input_v{"-".join(version.split("."))}.json'

    ### CMOR Tables
    cmor_tabpath = cwd + '/Tables/'
    cmor_tabname = 'obs4MIPs_Amon.json'

    ### Log file
    logfile = f'O4M/cmor_writer_{gas}_{version}.log'

    main(
        gas=gas, 
        cmor_tabpath=cmor_tabpath,
        cmor_tabname=cmor_tabname,
        input_file=input_file,
        input_json=input_json,
        logfile=logfile
        )